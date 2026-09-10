# {
#   "Seq": [
#     { "Depends": "py-lib-genlayermodelwrappers:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" },
#     { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
#   ]
# }
"""HOLDING — HoldingRegistry.

The canonical on-chain precedent registry for GenLayer Intelligent Contracts.

What this contract is
---------------------
A registry of *holdings*: finalised adjudications distilled into an issue, a set
of material facts, a verdict, a ratio and a set of reason codes, embedded and
stored in the native on-chain vector store (VecDB) so that the next panel can
retrieve them before it rules.

What this contract is not
-------------------------
It is not a consensus rule. GenLayer provides consensus; HOLDING provides
precedent. Nothing here binds a validator — a contract *chooses* to ask for
precedent and *chooses* to follow it. The distinguishing test is an application
rule enforced by the contract and the adjudication prompt, not by the protocol.

Finality
--------
A holding is created as UNVERIFIED (manual submission) or PENDING (submitted by
a registered source contract). It becomes FINAL only when an attestor records a
Consensus v0.6 finality attestation: transaction status code 7 (`Finalized`)
*together with* execution result `FINISHED_WITH_RETURN`. Only FINAL holdings are
returned by `get_precedent` and can be cited. This is what separates a
UNVERIFIED RECORD from a FINAL HOLDING, and it is the corpus-poisoning defence:
authority cannot be bought, because it starts at zero and only rises through
finality, appeal outcome, panel size, citations and consistency.

Cold start
----------
`get_precedent` returns `[]` when the registry is empty. It never fails. A
contract that asks for precedent on an empty registry adjudicates exactly as it
does today.

Generated file
--------------
This file is rendered from `contracts/HoldingRegistry.template.py` plus the
MIRRORED BLOCK in `shared/holding_core/_mirrored.py` by `scripts/render_contract.py`.
Edit the template or the mirrored block — never the generated file.
"""

from genlayer import *
import genlayermodelwrappers
import numpy as np
import re
import typing
from dataclasses import dataclass

# --- BEGIN MIRRORED BLOCK (contracts/HoldingRegistry.py) ---

SCHEMA_VERSION = "1.0.0"
BASIS = 10_000

WEIGHTS = {
    "finality": 3_000,
    "appeal": 2_500,
    "panel": 1_500,
    "citations": 2_000,
    "consistency": 1_000,
}

FINALITY_BY_STATUS = {
    "UNVERIFIED": 0,
    "PENDING": 2_500,
    "FINAL": 10_000,
    "REJECTED": 0,
}

APPEAL_BY_OUTCOME = {
    "NONE": 7_000,
    "UPHELD": 10_000,
    "OVERTURNED": 0,
    "PENDING": 5_000,
}

COMPONENT_ORDER = ["finality", "appeal", "panel", "citations", "consistency"]
REFERENCE_PANEL = 11
CITATION_SATURATION = 10
NEUTRAL_CONSISTENCY = 5_000

TX_STATUS_FINALIZED = 7
TX_EXECUTION_SUCCESS = "FINISHED_WITH_RETURN"


def normalize_text(text):
    if not isinstance(text, str):
        raise TypeError("normalize_text expects str")
    return " ".join(text.split()).strip()


def normalize_for_embedding(text):
    normalized = normalize_text(text).lower()
    normalized = re.sub(r"[^a-z0-9\s\-.,:;()\[\]]", " ", normalized)
    return " ".join(normalized.split())


def embedding_text(issue, facts_digest, verdict, ratio, contract_class=""):
    parts = [
        "schema:" + SCHEMA_VERSION,
        "contract_class:" + normalize_text(contract_class).lower(),
        "issue:" + normalize_for_embedding(issue),
        "facts:" + normalize_for_embedding(facts_digest),
        "verdict:" + normalize_text(verdict).upper(),
        "ratio:" + normalize_for_embedding(ratio),
    ]
    return "\n".join(parts)


def _finality_component(status):
    return FINALITY_BY_STATUS.get(str(status).upper(), 0)


def _appeal_component(appeal_outcome):
    return APPEAL_BY_OUTCOME.get(str(appeal_outcome).upper(), 0)


def _panel_component(panel_size):
    size = int(panel_size or 0)
    if size <= 0:
        return 0
    value = (size * BASIS) // REFERENCE_PANEL
    return BASIS if value > BASIS else value


def _citation_component(citations):
    count = int(citations or 0)
    if count <= 0:
        return 0
    value = (count * BASIS) // CITATION_SATURATION
    return BASIS if value > BASIS else value


def _consistency_component(followed, distinguished):
    total = int(followed or 0) + int(distinguished or 0)
    if total == 0:
        return NEUTRAL_CONSISTENCY
    return (int(followed) * BASIS) // total


def compute_components(status, appeal_outcome, panel_size, citations, followed, distinguished):
    return {
        "finality": _finality_component(status),
        "appeal": _appeal_component(appeal_outcome),
        "panel": _panel_component(panel_size),
        "citations": _citation_component(citations),
        "consistency": _consistency_component(followed, distinguished),
    }


def compute_authority_bp(components):
    total = 0
    for name in COMPONENT_ORDER:
        total += int(components.get(name, 0)) * WEIGHTS[name]
    return total // BASIS


def similarity_to_bp(value):
    if value is None:
        return 0
    if isinstance(value, bool):
        return 0
    text = str(value).strip()
    try:
        if "." in text:
            whole, frac = text.split(".", 1)
            frac = (frac + "0000")[:4]
            bp = int(whole) * BASIS + int(frac)
        else:
            bp = int(text)
            if bp <= 1:
                bp = bp * BASIS
    except ValueError:
        return 0
    if bp < 0:
        return 0
    return BASIS if bp > BASIS else bp


# --- END MIRRORED BLOCK (contracts/HoldingRegistry.py) ---

EMBEDDING_MODEL = "all-MiniLM-L6-v2"
EMBEDDING_DIM = 384
MAX_K = 10
MAX_FACTS_CHARS = 2000
MAX_ISSUE_CHARS = 300
MAX_RATIO_CHARS = 1200
SEP = "\u241f"


@allow_storage
@dataclass
class HoldingVector:
    holding_id: str
    domain: str


@allow_storage
@dataclass
class HoldingRecord:
    holding_id: str
    case_id: str
    source_contract: str
    source_tx: str
    domain: str
    contract_class: str
    issue: str
    facts_digest: str
    verdict: str
    ratio: str
    reason_codes: str
    evidence_hashes: str
    panel_size: u256
    status: str
    appeal_status: str
    appeal_outcome: str
    tx_status_code: u256
    execution_result: str
    finality_timestamp: u256
    created_at: u256
    authority_bp: u256
    citation_count: u256
    distinguishment_count: u256
    followed_count: u256
    holding_hash: str
    distinguishment: str


@allow_storage
@dataclass
class CitationRecord:
    source_holding_id: str
    target_holding_id: str
    relationship: str
    case_id: str
    created_at: u256


class HoldingRegistry(gl.Contract):
    owner: Address
    sequence: u256
    holdings: TreeMap[str, HoldingRecord]
    holding_ids: DynArray[str]
    citations: DynArray[CitationRecord]
    vector_store: VecDB[np.float32, typing.Literal[384], HoldingVector]
    source_contracts: TreeMap[Address, bool]
    attestors: TreeMap[Address, bool]
    case_index: TreeMap[str, str]
    relationship_index: TreeMap[str, bool]
    pending_links: TreeMap[str, str]

    def __init__(self, owner: str):
        self.owner = Address(owner)
        self.sequence = u256(0)

    # ------------------------------------------------------------------
    # internal helpers
    # ------------------------------------------------------------------
    def _require_owner(self) -> None:
        if gl.message.sender_address != self.owner:
            raise gl.UserError("HoldingRegistry: owner only")

    def _require_attestor(self) -> None:
        sender = gl.message.sender_address
        if sender != self.owner and not bool(self.attestors.get(sender, False)):
            raise gl.UserError("HoldingRegistry: attestor only")

    def _require_source_or_owner(self) -> None:
        sender = gl.message.sender_address
        if sender != self.owner and not bool(self.source_contracts.get(sender, False)):
            raise gl.UserError("HoldingRegistry: registered source contract or owner only")

    def _embed(self, text: str):
        """Pinned, deterministic embedding model.

        The model id is fixed contract state, so every validator computes the same
        vector and the k-NN is reproducible — which is exactly why retrieval
        belongs inside GenVM rather than behind an API.
        """
        return genlayermodelwrappers.SentenceTransformer(EMBEDDING_MODEL)(text)

    def _join(self, values) -> str:
        return SEP.join([str(v) for v in (values or [])])

    def _split(self, value: str):
        if value is None or value == "":
            return []
        return value.split(SEP)

    def _authority(self, record: HoldingRecord) -> int:
        return compute_authority_bp(
            compute_components(
                record.status,
                record.appeal_outcome,
                int(record.panel_size),
                int(record.citation_count),
                int(record.followed_count),
                int(record.distinguishment_count),
            )
        )

    def _refresh_authority(self, record: HoldingRecord) -> None:
        record.authority_bp = u256(self._authority(record))

    def _similarity_string(self, distance) -> str:
        bp = similarity_to_bp(str(1.0 - float(distance)))
        whole = bp // BASIS
        frac = bp - (whole * BASIS)
        return str(whole) + "." + str(frac).rjust(4, "0")

    def _record_to_dict(self, record: HoldingRecord) -> dict:
        return {
            "holding_id": record.holding_id,
            "case_id": record.case_id,
            "source_contract": record.source_contract,
            "source_tx": record.source_tx,
            "domain": record.domain,
            "contract_class": record.contract_class,
            "issue": record.issue,
            "facts_digest": record.facts_digest,
            "verdict": record.verdict,
            "ratio": record.ratio,
            "reason_codes": self._split(record.reason_codes),
            "evidence_hashes": self._split(record.evidence_hashes),
            "panel_size": int(record.panel_size),
            "status": record.status,
            "appeal_status": record.appeal_status,
            "appeal_outcome": record.appeal_outcome,
            "tx_status_code": int(record.tx_status_code),
            "execution_result": record.execution_result,
            "finality_timestamp": int(record.finality_timestamp),
            "created_at": int(record.created_at),
            "authority_bp": int(record.authority_bp),
            "citation_count": int(record.citation_count),
            "distinguishment_count": int(record.distinguishment_count),
            "followed_count": int(record.followed_count),
            "holding_hash": record.holding_hash,
            "distinguishment": record.distinguishment,
            "schema_version": SCHEMA_VERSION,
        }

    # ------------------------------------------------------------------
    # administration
    # ------------------------------------------------------------------
    @gl.public.write
    def register_source(self, address: str, allowed: bool) -> None:
        """Allow a contract to submit holdings (typically an adjudicator)."""
        self._require_owner()
        self.source_contracts[Address(address)] = bool(allowed)

    @gl.public.write
    def register_attestor(self, address: str, allowed: bool) -> None:
        """Allow an address to attest finality of a submitted record."""
        self._require_owner()
        self.attestors[Address(address)] = bool(allowed)

    @gl.public.write
    def transfer_ownership(self, new_owner: str) -> None:
        self._require_owner()
        self.owner = Address(new_owner)

    # ------------------------------------------------------------------
    # creation — never final on submission
    # ------------------------------------------------------------------
    @gl.public.write
    def create_holding(
        self,
        case_id: str,
        source_tx: str,
        domain: str,
        contract_class: str,
        issue: str,
        facts_digest: str,
        verdict: str,
        ratio: str,
        reason_codes: list[str],
        evidence_hashes: list[str],
        panel_size: int,
        appeal_status: str = "NONE",
        appeal_outcome: str = "NONE",
        distinguishment: str = "",
    ) -> str:
        """Create a holding record in a non-final state.

        Callable only by a registered source contract (or the owner). Duplicate
        (case_id, source_tx) pairs are rejected, which makes the call idempotent
        across appeal rounds where an emitted message may repeat.
        """
        self._require_source_or_owner()

        case_id = normalize_text(str(case_id))
        source_tx = normalize_text(str(source_tx))
        if case_id == "":
            raise gl.UserError("create_holding: case_id required")

        dedupe_key = case_id + "|" + source_tx
        existing = self.case_index.get(dedupe_key, "")
        if existing != "":
            raise gl.UserError("create_holding: holding already exists for this case")

        domain_value = str(domain).strip().lower()
        verdict_value = str(verdict).strip().upper()
        if verdict_value not in ("APPROVED", "REJECTED", "PARTIAL"):
            raise gl.UserError("create_holding: verdict must be APPROVED, REJECTED or PARTIAL")

        issue_value = normalize_text(str(issue))
        facts_value = normalize_text(str(facts_digest))
        ratio_value = normalize_text(str(ratio))
        if len(issue_value) < 8 or len(issue_value) > MAX_ISSUE_CHARS:
            raise gl.UserError("create_holding: issue length out of range")
        if len(facts_value) < 8 or len(facts_value) > MAX_FACTS_CHARS:
            raise gl.UserError("create_holding: facts digest length out of range")
        if len(ratio_value) < 20 or len(ratio_value) > MAX_RATIO_CHARS:
            raise gl.UserError("create_holding: ratio length out of range")
        if int(panel_size) < 1:
            raise gl.UserError("create_holding: panel_size must be at least 1")

        sender = gl.message.sender_address
        is_source = bool(self.source_contracts.get(sender, False))
        status = "PENDING" if is_source else "UNVERIFIED"

        self.sequence = u256(int(self.sequence) + 1)
        holding_id = "HLD-" + str(int(self.sequence)).rjust(6, "0")

        record = HoldingRecord(
            holding_id=holding_id,
            case_id=case_id,
            source_contract=str(sender),
            source_tx=source_tx,
            domain=domain_value,
            contract_class=str(contract_class),
            issue=issue_value,
            facts_digest=facts_value,
            verdict=verdict_value,
            ratio=ratio_value,
            reason_codes=self._join(reason_codes),
            evidence_hashes=self._join(evidence_hashes),
            panel_size=u256(int(panel_size)),
            status=status,
            appeal_status=str(appeal_status).upper(),
            appeal_outcome=str(appeal_outcome).upper(),
            tx_status_code=u256(0),
            execution_result="",
            finality_timestamp=u256(0),
            created_at=u256(int(gl.message.timestamp) if hasattr(gl.message, "timestamp") else 0),
            authority_bp=u256(0),
            citation_count=u256(0),
            distinguishment_count=u256(0),
            followed_count=u256(0),
            holding_hash="",
            distinguishment=normalize_text(str(distinguishment or "")),
        )
        self._refresh_authority(record)

        self.holdings[holding_id] = record
        self.holding_ids.append(holding_id)
        self.case_index[dedupe_key] = holding_id
        self.case_index["case:" + case_id] = holding_id

        text = embedding_text(issue_value, facts_value, verdict_value, ratio_value, contract_class)
        self.vector_store.insert(self._embed(text), HoldingVector(holding_id=holding_id, domain=domain_value))

        return holding_id

    # ------------------------------------------------------------------
    # finality attestation — the UNVERIFIED RECORD / FINAL HOLDING boundary
    # ------------------------------------------------------------------
    @gl.public.write
    def attest_finality(
        self,
        holding_id: str,
        tx_status_code: int,
        execution_result: str,
        finality_timestamp: int,
        appeal_outcome: str = "NONE",
        source_tx: str = "",
    ) -> str:
        """Promote a record to FINAL — or mark it REJECTED.

        Consensus v0.6: a transaction is settled when its status is 7 (Finalized)
        AND its execution result is FINISHED_WITH_RETURN. Status alone is not
        success; an accepted receipt can still contain a contract error.
        """
        self._require_attestor()
        record = self.holdings.get(holding_id, None)
        if record is None:
            raise gl.UserError("attest_finality: unknown holding")
        if record.status not in ("PENDING", "UNVERIFIED"):
            raise gl.UserError("attest_finality: holding already resolved")

        code = int(tx_status_code)
        execution = str(execution_result)
        if str(source_tx).strip() != "" and record.source_tx == "":
            record.source_tx = " ".join(str(source_tx).split()).strip()
        outcome = str(appeal_outcome).upper()

        record.tx_status_code = u256(code)
        record.execution_result = execution
        record.appeal_outcome = outcome
        record.finality_timestamp = u256(int(finality_timestamp))

        if code == TX_STATUS_FINALIZED and execution == TX_EXECUTION_SUCCESS:
            record.status = "FINAL"
            self._refresh_authority(record)
            self._resolve_pending_link(record)
        else:
            record.status = "REJECTED"
            self.pending_links["case:" + str(record.case_id)] = ""
            self._refresh_authority(record)
        return record.status

    @gl.public.write
    def reject_holding(self, holding_id: str, reason: str) -> str:
        """Mark a record as not eligible to be precedent."""
        self._require_attestor()
        record = self.holdings.get(holding_id, None)
        if record is None:
            raise gl.UserError("reject_holding: unknown holding")
        if record.status == "FINAL":
            raise gl.UserError("reject_holding: a final holding cannot be rejected")
        record.status = "REJECTED"
        record.appeal_outcome = "OVERTURNED"
        record.distinguishment = normalize_text(str(reason))
        self._refresh_authority(record)
        return record.status

    # ------------------------------------------------------------------
    # citation graph
    # ------------------------------------------------------------------
    @gl.public.write
    def cite(self, source_holding_id: str, target_holding_id: str, relationship: str, case_id: str) -> bool:
        """Record CITES / FOLLOWS / DISTINGUISHES between two final holdings."""
        self._require_source_or_owner()
        relationship = str(relationship).upper()
        if relationship not in ("CITES", "FOLLOWS", "DISTINGUISHES"):
            raise gl.UserError("cite: unsupported relationship")
        if source_holding_id == target_holding_id:
            raise gl.UserError("cite: a holding cannot relate to itself")

        source = self.holdings.get(source_holding_id, None)
        target = self.holdings.get(target_holding_id, None)
        if source is None or target is None:
            raise gl.UserError("cite: unknown holding")
        if source.status != "FINAL" or target.status != "FINAL":
            raise gl.UserError("cite: only final holdings may be related")
        return self._record_citation(source, target, relationship, case_id)

    def _record_citation(self, source, target, relationship: str, case_id: str) -> bool:
        """Write a precedent edge. Idempotent: a duplicate is a no-op."""
        relationship = str(relationship).upper()
        key = source.holding_id + "|" + target.holding_id + "|" + relationship
        if bool(self.relationship_index.get(key, False)):
            return False

        self.relationship_index[key] = True
        self.citations.append(
            CitationRecord(
                source_holding_id=source.holding_id,
                target_holding_id=target.holding_id,
                relationship=relationship,
                case_id=str(case_id),
                created_at=u256(int(finality_timestamp_or_zero())),
            )
        )

        if relationship == "DISTINGUISHES":
            target.distinguishment_count = u256(int(target.distinguishment_count) + 1)
        else:
            target.citation_count = u256(int(target.citation_count) + 1)
            if relationship == "FOLLOWS":
                target.followed_count = u256(int(target.followed_count) + 1)

        self._refresh_authority(target)
        self._refresh_authority(source)
        return True

    def _resolve_pending_link(self, record) -> bool:
        """Materialise a relationship declared before the holding id existed.

        The adjudicator must state FOLLOWS/DISTINGUISHES in the same transaction
        that emits the holding, at which point the holding is still PENDING. The
        intent is parked and only becomes an edge when the holding is final, so a
        proposal can never write to the precedent graph.
        """
        key = "case:" + str(record.case_id)
        pending = self.pending_links.get(key, "")
        if pending == "":
            return False
        self.pending_links[key] = ""
        parts = str(pending).split("|")
        if len(parts) != 3:
            return False
        target = self.holdings.get(parts[0], None)
        if target is None or target.status != "FINAL" or target.holding_id == record.holding_id:
            return False
        if parts[1] not in ("CITES", "FOLLOWS", "DISTINGUISHES"):
            return False
        return self._record_citation(record, target, parts[1], parts[2])

    @gl.public.write
    def cite_by_case(self, source_case_id: str, target_holding_id: str, relationship: str, case_id: str) -> bool:
        """Cite using the originating case id, so an adjudicator can declare the
        relationship in the same transaction that emits the holding (the holding
        id does not exist yet).

        The intent is parked in `pending_links` and materialises only when the
        holding for that case is attested FINAL — a proposal alone never writes
        to the precedent graph.
        """
        self._require_source_or_owner()
        relationship = str(relationship).upper()
        if relationship not in ("CITES", "FOLLOWS", "DISTINGUISHES"):
            raise gl.UserError("cite_by_case: unsupported relationship")
        if self.holdings.get(str(target_holding_id), None) is None:
            raise gl.UserError("cite_by_case: unknown target holding")
        self.pending_links["case:" + str(source_case_id)] = (
            str(target_holding_id) + "|" + relationship + "|" + str(case_id)
        )
        return False

    # ------------------------------------------------------------------
    # views
    # ------------------------------------------------------------------
    @gl.public.view
    def get_precedent(self, case_digest: str, domain: str, k: int) -> list[dict]:
        """Retrieve the nearest final holdings for a case digest.

        Cold start: returns [] when nothing is indexed. Deterministic: the
        embedding model is pinned and every validator recomputes the k-NN, so the
        panel cannot be shown a curated set of precedents.
        """
        k_int = int(k)
        if k_int < 1:
            k_int = 1
        if k_int > MAX_K:
            k_int = MAX_K

        query = normalize_for_embedding(str(case_digest))
        if query == "":
            return []

        embedding = self._embed(query)
        candidates = []
        for item in self.vector_store.knn(embedding, k_int * 4):
            record = self.holdings.get(item.value.holding_id, None)
            if record is None:
                continue
            if record.status != "FINAL":
                continue
            if domain != "" and domain != "all" and record.domain != domain:
                continue
            similarity_str = self._similarity_string(item.distance)
            candidates.append(
                {
                    "holding_id": record.holding_id,
                    "domain": record.domain,
                    "contract_class": record.contract_class,
                    "issue": record.issue,
                    "facts_digest": record.facts_digest,
                    "verdict": record.verdict,
                    "ratio": record.ratio,
                    "similarity": similarity_str,
                    "similarity_bp": similarity_to_bp(similarity_str),
                    "authority_bp": int(record.authority_bp),
                    "citation_count": int(record.citation_count),
                    "distinguishment_count": int(record.distinguishment_count),
                    "status": record.status,
                }
            )

        candidates.sort(key=lambda c: (-int(c["similarity_bp"]), -int(c["authority_bp"]), str(c["holding_id"])))
        return candidates[:k_int]

    @gl.public.view
    def get_holding(self, holding_id: str) -> dict:
        record = self.holdings.get(holding_id, None)
        if record is None:
            return {}
        return self._record_to_dict(record)

    @gl.public.view
    def get_holding_by_case(self, case_id: str) -> dict:
        """Resolve a case to the holding created from it (empty when none yet)."""
        holding_id = self.case_index.get("case:" + normalize_text(str(case_id)), "")
        if holding_id == "":
            return {}
        record = self.holdings.get(holding_id, None)
        return self._record_to_dict(record) if record is not None else {}

    @gl.public.view
    def get_holdings(self, limit: int = 100) -> list[dict]:
        out = []
        count = 0
        for holding_id in self.holding_ids:
            if count >= int(limit):
                break
            record = self.holdings.get(holding_id, None)
            if record is not None:
                out.append(self._record_to_dict(record))
                count += 1
        return out

    @gl.public.view
    def get_citations(self, holding_id: str) -> list[dict]:
        out = []
        for item in self.citations:
            if item.source_holding_id == holding_id or item.target_holding_id == holding_id:
                out.append(
                    {
                        "source_holding_id": item.source_holding_id,
                        "target_holding_id": item.target_holding_id,
                        "relationship": item.relationship,
                        "case_id": item.case_id,
                        "created_at": int(item.created_at),
                    }
                )
        return out

    @gl.public.view
    def get_distinguishments(self, holding_id: str) -> list[dict]:
        out = []
        for item in self.citations:
            if item.relationship == "DISTINGUISHES" and item.target_holding_id == holding_id:
                source = self.holdings.get(item.source_holding_id, None)
                out.append(
                    {
                        "holding_id": item.source_holding_id,
                        "case_id": item.case_id,
                        "issue": source.issue if source is not None else "",
                        "ratio": source.ratio if source is not None else "",
                        "verdict": source.verdict if source is not None else "",
                        "created_at": int(item.created_at),
                    }
                )
        return out

    @gl.public.view
    def is_registered_source(self, address: str) -> bool:
        return bool(self.source_contracts.get(Address(address), False))

    @gl.public.view
    def get_stats(self) -> dict:
        final_count = 0
        pending_count = 0
        rejected_count = 0
        for holding_id in self.holding_ids:
            record = self.holdings.get(holding_id, None)
            if record is None:
                continue
            if record.status == "FINAL":
                final_count += 1
            elif record.status == "REJECTED":
                rejected_count += 1
            else:
                pending_count += 1
        return {
            "sequence": int(self.sequence),
            "total": len(self.holding_ids),
            "final": final_count,
            "pending": pending_count,
            "rejected": rejected_count,
            "citations": len(self.citations),
            "schema_version": SCHEMA_VERSION,
            "embedding_model": EMBEDDING_MODEL,
            "embedding_dim": EMBEDDING_DIM,
        }


def finality_timestamp_or_zero() -> int:
    """Best-effort clock for relationship metadata; never affects ordering."""
    stamp = getattr(gl.message, "timestamp", 0)
    try:
        return int(stamp)
    except Exception:
        return 0
