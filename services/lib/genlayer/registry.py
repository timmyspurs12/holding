"""Typed facade over the HoldingRegistry contract (genlayerContracts).

Everything above this layer is app-facing JSON. Contract dicts are converted
here; raw blockchain objects never leave this module.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from shared.holding_core import authority as authority_core
from shared.holding_core import schema as holding_schema

from .base import Chain, ContractRejected
from .config import GenLayerConfig
from .types import (
    Authority,
    AuthorityBreakdown,
    Case,
    Citation,
    Finality,
    Holding,
    NetworkInfo,
    PrecedentHit,
    Provenance,
    RegistryStats,
    TxReceipt,
)

RELATIONSHIPS = ("CITES", "FOLLOWS", "DISTINGUISHES")


def authority_view(record: Dict[str, Any]) -> Authority:
    score_bp = int(record.get("authority_bp", 0) or 0)
    computed = authority_core.compute_authority(
        record.get("status", "UNVERIFIED"),
        record.get("appeal_outcome", "NONE"),
        int(record.get("panel_size", 0) or 0),
        int(record.get("citation_count", 0) or 0),
        int(record.get("followed_count", 0) or 0),
        int(record.get("distinguishment_count", 0) or 0),
    )
    return Authority(
        score=round(score_bp / 10_000, 4),
        score_bp=score_bp,
        band=computed["band"],
        components_bp=computed["components_bp"],
        weights_bp=computed["weights_bp"],
        breakdown=[AuthorityBreakdown(**row) for row in computed["breakdown"]],
        formula=computed["formula"],
        explanation=computed["explanation"],
    )


def holding_view(record: Dict[str, Any], *, mode: str, registry_address: str) -> Holding:
    record = dict(record)
    if not record:
        raise ContractRejected("holding not found")
    record.setdefault("contract_address", registry_address)
    record.setdefault("transaction_reference", record.get("source_tx") or "")
    canonical = holding_schema.canonical_holding(record)
    canonical["authority"] = authority_view(record).model_dump()
    provenance = dict(canonical["provenance"])
    provenance["mode"] = mode
    provenance["simulated"] = mode == "DEMO"
    canonical["provenance"] = provenance
    canonical["simulated"] = mode == "DEMO"
    canonical["finality"] = Finality(
        status=record.get("status", "UNVERIFIED"),
        tx_status_code=record.get("tx_status_code"),
        execution_result=record.get("execution_result", "") or "",
        finality_timestamp=record.get("finality_timestamp"),
        appeal_status=record.get("appeal_status", "NONE") or "NONE",
        appeal_outcome=record.get("appeal_outcome", "NONE") or "NONE",
    ).model_dump()
    return Holding(**canonical)


class HoldingRegistryContract:
    """Reads and writes, typed. The single place that knows the contract ABI."""

    def __init__(self, chain: Chain, config: GenLayerConfig) -> None:
        self.chain = chain
        self.config = config
        self.address = config.registry_address
        self.adjudicator_address = config.adjudicator_address

    # -- meta ---------------------------------------------------------
    def network_info(self) -> NetworkInfo:
        return self.config.info()

    def _mode(self) -> str:
        return self.config.mode.value

    # -- reads --------------------------------------------------------
    def stats(self) -> RegistryStats:
        raw = self.chain.read(self.address, "get_stats") or {}
        holdings = self.list_holdings(limit=10_000)
        follows = 0
        distinguishes = 0
        for holding in holdings:
            raw_record = self.chain.read(self.address, "get_holding", [holding.holding_id]) or {}
            follows += int(raw_record.get("followed_count", 0) or 0)
            distinguishes += int(raw_record.get("distinguishment_count", 0) or 0)
        statuses = [h.status for h in holdings]
        return RegistryStats(
            sequence=int(raw.get("sequence", 0) or 0),
            total=int(raw.get("total", 0) or 0),
            final=statuses.count("FINAL"),
            pending=statuses.count("PENDING"),
            rejected=statuses.count("REJECTED"),
            unverified=statuses.count("UNVERIFIED"),
            citations=int(raw.get("citations", 0) or 0),
            follows=follows,
            distinguishes=distinguishes,
            domains=len({h.domain for h in holdings if h.domain}),
            schema_version=str(raw.get("schema_version", "")),
            embedding_model=str(raw.get("embedding_model", "")),
            embedding_dim=int(raw.get("embedding_dim", 0) or 0),
            mode=self._mode(),
            simulated=self.chain.simulated,
        )

    def list_holdings(self, limit: int = 100) -> List[Holding]:
        raw = self.chain.read(self.address, "get_holdings", [int(limit)]) or []
        return [holding_view(item, mode=self._mode(), registry_address=self.address) for item in raw]

    def get_holding(self, holding_id: str) -> Optional[Holding]:
        holding_id = str(holding_id).strip().upper()
        if not holding_schema.is_valid_holding_id(holding_id):
            return None
        raw = self.chain.read(self.address, "get_holding", [holding_id])
        if not raw:
            return None
        return holding_view(raw, mode=self._mode(), registry_address=self.address)

    def get_precedent(self, case_digest: str, domain: str = "", k: int = 3) -> List[PrecedentHit]:
        """Contract-side retrieval. Cold start returns [] — never raises."""
        try:
            raw = self.chain.read(self.address, "get_precedent", [str(case_digest), str(domain), int(k)]) or []
        except ContractRejected:
            return []
        hits: List[PrecedentHit] = []
        for item in raw:
            record = self.chain.read(self.address, "get_holding", [item.get("holding_id")]) or item
            record = dict(record)
            record.update({key: item[key] for key in ("similarity", "authority_bp") if key in item})
            view = holding_view(record, mode=self._mode(), registry_address=self.address)
            hits.append(
                PrecedentHit(
                    holding_id=view.holding_id,
                    display_id=view.display_id,
                    case_id=view.case_id,
                    domain=view.domain,
                    issue=view.issue,
                    ratio=view.ratio,
                    verdict=view.verdict,
                    similarity=round(int(item.get("similarity_bp", 0) or 0) / 10_000, 4),
                    similarity_bp=int(item.get("similarity_bp", 0) or 0),
                    authority_bp=int(item.get("authority_bp", 0) or 0),
                    authority=view.authority,
                    status=view.status,
                    citation_count=view.citation_count,
                    distinguishment_count=view.distinguishment_count,
                    created_at=view.created_at,
                )
            )
        return hits

    def get_citations(self, holding_id: str) -> List[Citation]:
        raw = self.chain.read(self.address, "get_citations", [str(holding_id)]) or []
        out = []
        for item in raw:
            direction = "outgoing" if item.get("source_holding_id") == holding_id else "incoming"
            out.append(
                Citation(
                    source_holding_id=item.get("source_holding_id", ""),
                    target_holding_id=item.get("target_holding_id", ""),
                    relationship=item.get("relationship", "CITES"),
                    case_id=item.get("case_id", ""),
                    created_at=int(item.get("created_at", 0) or 0),
                    direction=direction,
                )
            )
        return out

    def get_distinguishments(self, holding_id: str) -> List[Dict[str, Any]]:
        raw = self.chain.read(self.address, "get_distinguishments", [str(holding_id)]) or []
        out = []
        for item in raw:
            detail = self.get_holding(item.get("holding_id", ""))
            out.append(
                {
                    "holding_id": item.get("holding_id", ""),
                    "case_id": item.get("case_id", ""),
                    "issue": item.get("issue", ""),
                    "ratio": item.get("ratio", ""),
                    "verdict": item.get("verdict", ""),
                    "created_at": int(item.get("created_at", 0) or 0),
                    "reason": (detail.distinguishment if detail else ""),
                    "simulated": self.chain.simulated,
                }
            )
        return out

    # -- cases (the adjudicator consumer contract) --------------------
    def list_cases(self) -> List[str]:
        try:
            return list(self.chain.read(self.adjudicator_address, "get_case_ids") or [])
        except ContractRejected:
            return []

    def get_case(self, case_id: str) -> Optional[Case]:
        try:
            raw = self.chain.read(self.adjudicator_address, "get_case", [str(case_id)]) or {}
        except ContractRejected:
            return None
        if not raw:
            return None
        return Case(
            case_id=raw.get("case_id", case_id),
            status=raw.get("status", "PROPOSED"),
            domain=raw.get("domain", ""),
            contract_class=raw.get("contract_class", ""),
            facts=list(raw.get("facts", [])),
            verdict=raw.get("verdict", ""),
            ratio=raw.get("ratio", ""),
            issue=raw.get("issue", ""),
            reason_codes=list(raw.get("reason_codes", [])),
            precedent_used=list(raw.get("precedent_used", [])),
            followed=bool(raw.get("followed", False)),
            distinguished=bool(raw.get("distinguished", False)),
            distinguishment_reason=raw.get("distinguishment", "") or "",
            reasoning=raw.get("reasoning", "") or "",
            panel_size=int(raw.get("panel_size", 0) or 0),
            submitted_at=raw.get("submitted_at") or None,
            holding_id=raw.get("holding_id") or None,
            simulated=self.chain.simulated,
        )

    # -- writes -------------------------------------------------------
    def create_holding(
        self,
        *,
        case_id: str,
        source_tx: str,
        domain: str,
        contract_class: str,
        issue: str,
        facts_digest: str,
        verdict: str,
        ratio: str,
        reason_codes: Sequence[str] = (),
        evidence_hashes: Sequence[str] = (),
        panel_size: int = 1,
        appeal_status: str = "NONE",
        appeal_outcome: str = "NONE",
        distinguishment: str = "",
        sender: str = "",
    ):
        args = [
            case_id,
            source_tx,
            domain,
            contract_class,
            issue,
            facts_digest,
            verdict,
            ratio,
            list(reason_codes),
            list(evidence_hashes),
            int(panel_size),
            appeal_status,
            appeal_outcome,
            distinguishment,
        ]
        return self.chain.write(self.address, "create_holding", args, sender=sender)

    def attest_finality(
        self,
        *,
        holding_id: str,
        tx_status_code: int,
        execution_result: str,
        finality_timestamp: int,
        appeal_outcome: str = "NONE",
        source_tx: str = "",
        sender: str = "",
    ):
        args = [
            holding_id,
            int(tx_status_code),
            str(execution_result),
            int(finality_timestamp),
            appeal_outcome,
            source_tx,
        ]
        return self.chain.write(self.address, "attest_finality", args, sender=sender)

    def cite(self, *, source_holding_id: str, target_holding_id: str, relationship: str, case_id: str, sender: str = ""):
        relationship = str(relationship).upper()
        if relationship not in RELATIONSHIPS:
            raise ContractRejected(f"unsupported relationship {relationship!r}")
        return self.chain.write(
            self.address, "cite", [source_holding_id, target_holding_id, relationship, case_id], sender=sender
        )

    def reject_holding(self, *, holding_id: str, reason: str, sender: str = ""):
        return self.chain.write(self.address, "reject_holding", [holding_id, reason], sender=sender)

    # -- the loop (used by the demo runner and the simulation endpoint) --
    def submit_case(self, case_id: str, facts: Sequence[str], sender: str = ""):
        return self.chain.write(self.adjudicator_address, "submit_case", [case_id, list(facts)], sender=sender)

    def adjudicate(self, case_id: str, sender: str = ""):
        return self.chain.write(self.adjudicator_address, "adjudicate", [case_id], sender=sender)


def provenance_of(holding: Holding) -> Provenance:
    return holding.provenance
