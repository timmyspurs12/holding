"""Search and filtering for the Reporter.

Retrieval itself stays in the contract: `get_precedent()` embeds the query with
the pinned model and searches the on-chain VecDB. This module only applies
metadata filters and shapes the response — the frontend never decides what
matters.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from ..lib.genlayer.registry import HoldingRegistryContract
from ..lib.genlayer.types import Holding, PrecedentHit

SORTS = {
    "authority": lambda h: (-h.authority_bp, h.holding_id),
    "newest": lambda h: (-(h.finality_timestamp or h.created_at or 0), h.holding_id),
    "oldest": lambda h: ((h.finality_timestamp or h.created_at or 0), h.holding_id),
    "citations": lambda h: (-h.citation_count, h.holding_id),
    "id": lambda h: h.holding_id,
}


class SearchQuery:
    def __init__(
        self,
        *,
        q: str = "",
        domain: str = "",
        contract_class: str = "",
        status: str = "",
        verdict: str = "",
        appeal_outcome: str = "",
        min_authority: Optional[float] = None,
        max_authority: Optional[float] = None,
        since: Optional[int] = None,
        until: Optional[int] = None,
        k: int = 10,
        sort: str = "authority",
    ) -> None:
        self.q = (q or "").strip()
        self.domain = (domain or "").strip().lower()
        self.contract_class = (contract_class or "").strip().lower()
        self.status = (status or "").strip().upper()
        self.verdict = (verdict or "").strip().upper()
        self.appeal_outcome = (appeal_outcome or "").strip().upper()
        self.min_authority = min_authority
        self.max_authority = max_authority
        self.since = since
        self.until = until
        self.k = max(1, min(int(k), 50))
        self.sort = sort if sort in SORTS else "authority"

    def effective_status(self) -> str:
        """Semantic retrieval only ever returns settled precedent.

        A caller can still ask for pending or rejected records explicitly, but
        an unqualified search must not surface them as if they were precedent.
        """
        return self.status or ("FINAL" if self.q else "")

    def matches(self, holding: Holding) -> bool:
        if self.domain and holding.domain != self.domain:
            return False
        if self.contract_class and holding.contract_class.lower() != self.contract_class:
            return False
        status = self.effective_status()
        if status and holding.status != status:
            return False
        if self.verdict and holding.verdict != self.verdict:
            return False
        if self.appeal_outcome and (holding.finality.get("appeal_outcome") or "NONE") != self.appeal_outcome:
            return False
        score = holding.authority_bp / 10_000
        if self.min_authority is not None and score < self.min_authority:
            return False
        if self.max_authority is not None and score > self.max_authority:
            return False
        stamp = holding.finality_timestamp or holding.created_at
        if self.since is not None and (stamp or 0) < self.since:
            return False
        if self.until is not None and (stamp or 0) > self.until:
            return False
        return True


def _hit(holding: Holding, similarity: Optional[float] = None) -> Dict[str, Any]:
    payload = holding.model_dump()
    payload["similarity"] = similarity
    return payload


def search(registry: HoldingRegistryContract, query: SearchQuery) -> List[Dict[str, Any]]:
    """Semantic when there is a query, catalogue when there is not.

    Cold start: an empty registry returns [] and never raises.
    """
    if not query.q:
        holdings = [h for h in registry.list_holdings(limit=10_000) if query.matches(h)]
        holdings.sort(key=SORTS[query.sort])
        return [_hit(h) for h in holdings[: query.k]]

    # Contract-side embedding + VecDB k-NN, over-fetched so metadata filters
    # can be applied without losing recall.
    candidates = registry.get_precedent(query.q, query.domain, min(query.k * 4, 50))
    by_id = {hit.holding_id: hit for hit in candidates}
    holdings: List[Holding] = []
    for hit in candidates:
        record = registry.get_holding(hit.holding_id)
        if record is not None and query.matches(record):
            holdings.append(record)

    # Metadata-only matches that the vector search did not surface are appended,
    # ranked after the semantic hits.
    seen = {h.holding_id for h in holdings}
    for holding in registry.list_holdings(limit=10_000):
        if holding.holding_id in seen or not query.matches(holding):
            continue
        if not _keyword_overlap(holding, query.q):
            continue
        holdings.append(holding)
        seen.add(holding.holding_id)

    ranked: List[Dict[str, Any]] = []
    for holding in holdings:
        hit = by_id.get(holding.holding_id)
        ranked.append(_hit(holding, hit.similarity if hit else None))
    ranked.sort(key=lambda item: (-(item["similarity"] or 0), -item["authority_bp"], item["holding_id"]))
    return ranked[: query.k]


def _keyword_overlap(holding: Holding, query: str) -> bool:
    tokens = {token for token in query.lower().replace("/", " ").split() if len(token) > 2}
    if not tokens:
        return False
    haystack = " ".join(
        [holding.issue, holding.ratio, holding.facts_digest, holding.domain, holding.contract_class, holding.verdict]
    ).lower()
    return any(token in haystack for token in tokens)


def precedent_view(registry: HoldingRegistryContract, holding: Holding, k: int) -> List[PrecedentHit]:
    """What the panel would have been shown for this holding's facts."""
    digest = " ".join([holding.issue, holding.facts_digest, holding.ratio, holding.verdict])
    return registry.get_precedent(digest, holding.domain, k)
