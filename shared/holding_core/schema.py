"""Canonical HOLDING schema.

This module is the single definition of what a holding is. It is imported by the
API, the indexer and the tests. The Intelligent Contract in `contracts/HoldingRegistry.py`
mirrors the parts it needs at runtime (see tests/test_mirror_sync.py) because a
GenLayer contract is deployed as one file and cannot import local modules.

Determinism rules
-----------------
Everything here must behave identically on every validator node:

* integers only — no floats in any value that reaches contract state
* no dict iteration order dependence, no sets, no time.time(), no randomness
* string comparison and sorting are byte-wise
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Dict, Iterable, List, Sequence

from ._mirrored import (  # noqa: F401  (mirrored with the contract)
    BASIS,
    FINALITY_BY_STATUS,
    APPEAL_BY_OUTCOME,
    COMPONENT_ORDER,
    SCHEMA_VERSION,
    TX_EXECUTION_SUCCESS,
    TX_STATUS_FINALIZED,
    WEIGHTS,
    embedding_text,
    normalize_for_embedding,
    normalize_text,
    similarity_to_bp,
)

# --------------------------------------------------------------------------
# enums
# --------------------------------------------------------------------------
VERDICTS = ("APPROVED", "REJECTED", "PARTIAL")
APPEAL_OUTCOMES = ("NONE", "UPHELD", "OVERTURNED", "PENDING")
HOLDING_STATUSES = (
    "UNVERIFIED",  # submitted, finality not yet attested
    "PENDING",     # submitted, awaiting finality attestation
    "FINAL",       # finality attested: eligible to be precedent
    "REJECTED",    # attested as failed / not eligible
)
RELATIONSHIPS = ("CITES", "FOLLOWS", "DISTINGUISHES")

# Consensus v0.6 transaction status codes (numeric) — see docs:
# https://docs.genlayer.com/understand-genlayer-protocol/core-concepts/transactions/transaction-statuses
TX_STATUS_FINALIZED = 7
TX_EXECUTION_SUCCESS = "FINISHED_WITH_RETURN"

# --------------------------------------------------------------------------
# field limits — keep canonical state small; large text is referenced by hash
# --------------------------------------------------------------------------
LIMITS = {
    "case_id": (1, 96),
    "domain": (2, 48),
    "contract_class": (2, 64),
    "issue": (8, 300),
    "facts_digest": (8, 2000),
    "verdict": (4, 16),
    "ratio": (20, 1200),
    "reason_code": (3, 48),
    "reason_codes": (0, 8),
    "evidence_hash": (8, 96),
    "evidence_hashes": (0, 16),
    "source_tx": (8, 96),
    "distinguishment": (40, 1200),
}

REASON_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
HEX_RE = re.compile(r"^(0x)?[0-9a-fA-F]{8,96}$")
HOLDING_ID_RE = re.compile(r"^HLD-\d{6}$")

ID_PREFIX = "HLD-"
ID_DIGITS = 6


# --------------------------------------------------------------------------
# normalisation
# --------------------------------------------------------------------------
def normalize_domain(domain: str) -> str:
    normalized = normalize_text(domain).lower().replace("_", "-").replace(" ", "-")
    normalized = re.sub(r"[^a-z0-9-]", "", normalized)
    return re.sub(r"-+", "-", normalized).strip("-")


def sha256_hex(value: str) -> str:
    return "0x" + hashlib.sha256(value.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# ids
# --------------------------------------------------------------------------
def make_holding_id(sequence: int) -> str:
    """HLD-000184 — zero padded so lexical order equals numeric order."""
    if not isinstance(sequence, int) or isinstance(sequence, bool):
        raise TypeError("sequence must be an int")
    if sequence < 0 or sequence >= 10**ID_DIGITS:
        raise ValueError("sequence out of range")
    return f"{ID_PREFIX}{sequence:0{ID_DIGITS}d}"


def holding_id_sequence(holding_id: str) -> int:
    if not is_valid_holding_id(holding_id):
        raise ValueError(f"invalid holding id: {holding_id!r}")
    return int(holding_id[len(ID_PREFIX) :])


def is_valid_holding_id(holding_id: str) -> bool:
    return isinstance(holding_id, str) and bool(HOLDING_ID_RE.match(holding_id))


def display_id(holding_id: str) -> str:
    """00184 — the form the Reporter shows."""
    return holding_id[len(ID_PREFIX) :] if is_valid_holding_id(holding_id) else holding_id


# --------------------------------------------------------------------------
# canonical text + hash
# --------------------------------------------------------------------------
def holding_hash(fields: Dict[str, Any]) -> str:
    """Content hash of the canonical fields — the integrity anchor for provenance."""
    ordered = [
        fields.get("case_id", ""),
        fields.get("source_contract", ""),
        fields.get("source_tx", ""),
        fields.get("domain", ""),
        fields.get("contract_class", ""),
        fields.get("issue", ""),
        fields.get("facts_digest", ""),
        fields.get("verdict", ""),
        fields.get("ratio", ""),
        "|".join(fields.get("reason_codes", [])),
        "|".join(fields.get("evidence_hashes", [])),
        str(fields.get("panel_size", 0)),
    ]
    return sha256_hex("\u241f".join(str(o) for o in ordered))


# --------------------------------------------------------------------------
# serialisation helpers
# --------------------------------------------------------------------------
def canonical_holding(record: Dict[str, Any]) -> Dict[str, Any]:
    """Return the app-facing (JSON) shape of a holding. Stable key order."""
    return {
        "holding_id": record["holding_id"],
        "display_id": display_id(record["holding_id"]),
        "case_id": record["case_id"],
        "contract_address": record.get("contract_address") or record.get("source_contract"),
        "transaction_reference": record.get("transaction_reference") or record.get("source_tx"),
        "domain": record.get("domain", ""),
        "contract_class": record.get("contract_class", ""),
        "issue": record.get("issue", ""),
        "facts_digest": record.get("facts_digest", ""),
        "verdict": record.get("verdict", ""),
        "reason_codes": list(record.get("reason_codes", [])),
        "ratio": record.get("ratio", ""),
        "evidence_hashes": list(record.get("evidence_hashes", [])),
        "panel_size": int(record.get("panel_size", 0) or 0),
        "status": record.get("status", "UNVERIFIED"),
        "appeal_status": record.get("appeal_status", "NONE"),
        "appeal_outcome": record.get("appeal_outcome", "NONE"),
        "finality_timestamp": record.get("finality_timestamp"),
        "created_at": record.get("created_at"),
        "authority_bp": int(record.get("authority_bp", 0) or 0),
        "finality": {
            "status": record.get("status", "UNVERIFIED"),
            "tx_status_code": record.get("tx_status_code"),
            "execution_result": record.get("execution_result"),
            "finality_timestamp": record.get("finality_timestamp"),
        },
        "authority": record.get("authority", {}),
        "citation_count": record.get("citation_count", 0),
        "distinguishment_count": record.get("distinguishment_count", 0),
        "parent_holdings": list(record.get("parent_holdings", [])),
        "provenance": {
            "case_id": record.get("case_id", ""),
            "source_contract": record.get("source_contract") or record.get("contract_address"),
            "source_tx": record.get("source_tx") or record.get("transaction_reference"),
            "holding_hash": record.get("holding_hash"),
            "created_at": record.get("created_at"),
            "schema_version": SCHEMA_VERSION,
        },
        "distinguishment": record.get("distinguishment") or "",
        "embedding_vector_ref": record.get("embedding_vector_ref") or "",
    }


def clamp_int(value: int, low: int, high: int) -> int:
    return low if value < low else high if value > high else value


def as_str_list(value: Iterable[Any]) -> List[str]:
    return [str(v) for v in (value or [])]
