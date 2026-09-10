"""Validation for adjudication output and holding payloads.

The rule: nothing enters the canonical registry unless it parses against the
schema. The frontend can never create a holding — only a registered source
contract (or an attestor with a verified finalized transaction) can, and its
payload still has to pass these checks.

Mirrored (subset) inside contracts/HoldingRegistry.py; tests/test_mirror_sync.py
fails if the two drift.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Sequence, Tuple

from . import schema

REQUIRED_ADJUDICATION_KEYS = ("issue", "facts", "verdict", "ratio", "reason_codes")

# Distinguishments must be concrete. These are the phrases the brief calls out as
# "different because this case is different" — they carry no material difference.
GENERIC_DISTINGUISHMENTS = (
    "the circumstances differ",
    "circumstances are different",
    "this case is different",
    "different because this case is different",
    "the facts differ",
    "not applicable here",
    "does not apply here",
    "different situation",
)

# A concrete distinguishment names a material difference. Minimum length is a
# crude proxy for "said something" — the real check is the generic-phrase list
# plus the requirement that it mention at least one difference cue.
DIFFERENCE_CUES = (
    "unlike",
    "whereas",
    "in this case",
    "here,",
    "however",
    "instead",
    "by contrast",
    "materially",
    "already",
    "never",
    "before cancellation",
    "after cancellation",
    "not yet",
    "fully delivered",
    "partially",
)


class ValidationError(ValueError):
    """Raised when a payload does not conform to the canonical schema."""

    def __init__(self, errors: Sequence[str]):
        self.errors = list(errors)
        super().__init__("; ".join(self.errors))


def _check_length(field: str, value: str, errors: List[str]) -> None:
    limits = schema.LIMITS.get(field)
    if not limits:
        return
    low, high = limits
    length = len(value)
    if length < low or length > high:
        errors.append(f"{field}: length {length} outside {low}..{high}")


def validate_reason_codes(codes: Any, errors: List[str]) -> List[str]:
    if codes is None:
        return []
    if not isinstance(codes, (list, tuple)):
        errors.append("reason_codes: must be a list of strings")
        return []
    low, high = schema.LIMITS["reason_codes"]
    if not (low <= len(codes) <= high):
        errors.append(f"reason_codes: count {len(codes)} outside {low}..{high}")
    cleaned: List[str] = []
    for code in codes:
        code_str = str(code).strip().upper()
        if not schema.REASON_CODE_RE.match(code_str):
            errors.append(f"reason_codes: {code!r} is not UPPER_SNAKE_CASE")
            continue
        _check_length("reason_code", code_str, errors)
        cleaned.append(code_str)
    return cleaned


def validate_evidence_hashes(hashes: Any, errors: List[str]) -> List[str]:
    if hashes is None:
        return []
    if not isinstance(hashes, (list, tuple)):
        errors.append("evidence_hashes: must be a list of strings")
        return []
    low, high = schema.LIMITS["evidence_hashes"]
    if not (low <= len(hashes) <= high):
        errors.append(f"evidence_hashes: count {len(hashes)} outside {low}..{high}")
    cleaned: List[str] = []
    for item in hashes:
        item_str = str(item).strip()
        if not schema.HEX_RE.match(item_str):
            errors.append(f"evidence_hashes: {item!r} is not a hash reference")
            continue
        cleaned.append(item_str)
    return cleaned


def validate_adjudication_payload(payload: Any) -> Dict[str, Any]:
    """Validate the structured output of an adjudication.

    Returns the normalised payload. Raises ValidationError if malformed.
    """
    errors: List[str] = []
    if not isinstance(payload, dict):
        raise ValidationError(["payload: must be a JSON object"])

    missing = [k for k in REQUIRED_ADJUDICATION_KEYS if k not in payload]
    if missing:
        errors.append(f"missing required keys: {', '.join(sorted(missing))}")
        raise ValidationError(errors)

    issue = payload["issue"]
    if not isinstance(issue, str):
        errors.append("issue: must be a string")
        issue = ""
    else:
        issue = schema.normalize_text(issue)
        _check_length("issue", issue, errors)

    facts = payload["facts"]
    if not isinstance(facts, (list, tuple)) or not facts:
        errors.append("facts: must be a non-empty list of strings")
        facts = []
    facts = [schema.normalize_text(str(f)) for f in facts if str(f).strip()]
    if len(facts) > 12:
        errors.append("facts: at most 12 material facts")
    for fact in facts:
        if len(fact) < 3:
            errors.append(f"facts: {fact!r} is too short")

    verdict = str(payload["verdict"]).strip().upper()
    if verdict not in schema.VERDICTS:
        errors.append(f"verdict: {verdict!r} not in {schema.VERDICTS}")

    ratio = payload["ratio"]
    if not isinstance(ratio, str):
        errors.append("ratio: must be a string")
        ratio = ""
    else:
        ratio = schema.normalize_text(ratio)
        _check_length("ratio", ratio, errors)

    reason_codes = validate_reason_codes(payload.get("reason_codes"), errors)

    if errors:
        raise ValidationError(errors)

    return {
        "issue": issue,
        "facts": facts,
        "verdict": verdict,
        "ratio": ratio,
        "reason_codes": reason_codes,
    }


def validate_distinguishment(text: Any, required: bool = False) -> Tuple[str, List[str]]:
    """A distinguishment must state a concrete material difference."""
    errors: List[str] = []
    if text is None or (isinstance(text, str) and not text.strip()):
        if required:
            errors.append("distinguishment: required when departing from precedent")
        return "", errors

    if not isinstance(text, str):
        errors.append("distinguishment: must be a string")
        return "", errors

    cleaned = schema.normalize_text(text)
    low, high = schema.LIMITS["distinguishment"]
    if len(cleaned) < low:
        errors.append(
            f"distinguishment: {len(cleaned)} characters is too short to state a material difference "
            f"(minimum {low})"
        )
    if len(cleaned) > high:
        errors.append(f"distinguishment: length {len(cleaned)} exceeds {high}")

    lowered = cleaned.lower()
    for phrase in GENERIC_DISTINGUISHMENTS:
        if phrase in lowered:
            errors.append(
                f"distinguishment: {phrase!r} does not identify a material difference"
            )
            break

    if not any(cue in lowered for cue in DIFFERENCE_CUES):
        errors.append(
            "distinguishment: must state what is materially different, not merely that it differs"
        )

    return cleaned, errors


def validate_holding_creation(
    *,
    case_id: str,
    domain: str,
    contract_class: str,
    issue: str,
    facts_digest: str,
    verdict: str,
    ratio: str,
    panel_size: Any,
    source_tx: str = "",
    reason_codes: Any = None,
    evidence_hashes: Any = None,
) -> Dict[str, Any]:
    """Validate everything required to create a holding record."""
    errors: List[str] = []

    case_id = schema.normalize_text(str(case_id))
    _check_length("case_id", case_id, errors)
    if not case_id:
        errors.append("case_id: must not be empty")

    normalized_domain = schema.normalize_domain(str(domain))
    if not normalized_domain:
        errors.append("domain: must be a non-empty slug")

    contract_class = schema.normalize_text(str(contract_class))
    _check_length("contract_class", contract_class, errors)

    issue = schema.normalize_text(str(issue))
    _check_length("issue", issue, errors)

    facts_digest = schema.normalize_text(str(facts_digest))
    _check_length("facts_digest", facts_digest, errors)

    verdict = str(verdict).strip().upper()
    if verdict not in schema.VERDICTS:
        errors.append(f"verdict: {verdict!r} not in {schema.VERDICTS}")

    ratio = schema.normalize_text(str(ratio))
    _check_length("ratio", ratio, errors)

    try:
        panel_size_int = int(panel_size)
    except (TypeError, ValueError):
        errors.append("panel_size: must be an integer")
        panel_size_int = 0
    if panel_size_int < 1 or panel_size_int > 128:
        errors.append("panel_size: outside 1..128")

    source_tx = schema.normalize_text(str(source_tx or ""))
    if source_tx and not schema.HEX_RE.match(source_tx):
        errors.append("source_tx: must be a hex transaction id")

    codes = validate_reason_codes(reason_codes, errors)
    hashes = validate_evidence_hashes(evidence_hashes, errors)

    if errors:
        raise ValidationError(errors)

    return {
        "case_id": case_id,
        "domain": normalized_domain,
        "contract_class": contract_class,
        "issue": issue,
        "facts_digest": facts_digest,
        "verdict": verdict,
        "ratio": ratio,
        "panel_size": panel_size_int,
        "source_tx": source_tx,
        "reason_codes": codes,
        "evidence_hashes": hashes,
    }


def validate_relationship(
    source_id: str, target_id: str, relationship: str, known_ids: Sequence[str]
) -> List[str]:
    errors: List[str] = []
    relationship = str(relationship).strip().upper()
    if relationship not in schema.RELATIONSHIPS:
        errors.append(f"relationship: {relationship!r} not in {schema.RELATIONSHIPS}")
    if not schema.is_valid_holding_id(source_id):
        errors.append(f"source_holding_id: {source_id!r} is not a valid holding id")
    if not schema.is_valid_holding_id(target_id):
        errors.append(f"target_holding_id: {target_id!r} is not a valid holding id")
    if source_id == target_id:
        errors.append("relationship: a holding cannot relate to itself")
    if known_ids is not None:
        if source_id and source_id not in known_ids:
            errors.append(f"source_holding_id: {source_id} is not in the registry")
        if target_id and target_id not in known_ids:
            errors.append(f"target_holding_id: {target_id} is not in the registry")
    return errors


def is_finality_attestation_valid(tx_status_code: Any, execution_result: Any) -> bool:
    """Consensus v0.6: finalized AND the contract call itself succeeded."""
    try:
        code = int(tx_status_code)
    except (TypeError, ValueError):
        return False
    return code == schema.TX_STATUS_FINALIZED and str(execution_result) == schema.TX_EXECUTION_SUCCESS
