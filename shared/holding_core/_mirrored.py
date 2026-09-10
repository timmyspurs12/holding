"""MIRRORED BLOCK — the single source of truth shared with the contract.

Everything between the BEGIN/END markers below is reproduced **verbatim** in
`contracts/HoldingRegistry.py`. A GenLayer Intelligent Contract is deployed as one
file and cannot import local modules, so the contract carries its own copy.
`tests/test_mirror_sync.py` extracts both blocks and fails the build if they drift.

Rules for anything inside the block:
  * stdlib only (re, hashlib) — no imports beyond those already at the top
  * integers only for anything that reaches contract state
  * no I/O, no time, no randomness, no iteration over dicts for ordering
"""

from __future__ import annotations

import re

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
