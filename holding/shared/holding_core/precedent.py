"""Precedent retrieval ordering and the adjudication prompt.

Two halves:

1. `rank_precedents` — the deterministic ordering rule applied *after* the
   on-chain k-NN. The contract does the vector search (inside GenVM, so it is
   consensus-verified); this decides what survives filtering and in what order.
   It is mirrored in the contract and re-applied off-chain so the Reporter shows
   exactly what a panel would see.

2. `build_adjudication_prompt` — the instruction that makes the distinguishing
   test real. The contract and the backend must send the same prompt, so the
   prompt lives here and the Adjudicator contract mirrors it.

Similarity is handled as an integer in basis points (0..10_000). The contract
returns similarity as a *string* because floats are not safe in consensus state.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Iterable, List, Optional, Sequence

from . import schema

from ._mirrored import BASIS, similarity_to_bp

MAX_CANDIDATES = 64
DEFAULT_K = 3
MAX_K = 10


def bp_to_similarity(bp: int) -> float:
    return round(bp / BASIS, 4)


def _domain_match(candidate_domain: str, requested: str) -> int:
    """1 when the candidate is in the requested domain, 0 otherwise."""
    if not requested or requested == "all":
        return 1
    return 1 if candidate_domain == requested else 0


def rank_precedents(
    candidates: Iterable[Dict[str, Any]],
    k: int = DEFAULT_K,
    domain: str = "",
) -> List[Dict[str, Any]]:
    """Deterministic ordering: final holdings only, same domain first, then
    similarity desc, authority desc, holding_id asc (stable tie-break)."""
    k = 1 if k < 1 else MAX_K if k > MAX_K else k
    pool: List[Dict[str, Any]] = []
    for item in candidates:
        if str(item.get("status", "")).upper() != "FINAL":
            continue
        pool.append(item)
    if not pool:
        return []

    def sort_key(item: Dict[str, Any]):
        return (
            -_domain_match(str(item.get("domain", "")), schema.normalize_domain(domain or "")),
            -similarity_to_bp(item.get("similarity")),
            -int(item.get("authority_bp", 0) or 0),
            str(item.get("holding_id", "")),
        )

    pool.sort(key=sort_key)
    ranked = pool[:k]
    for item in ranked:
        item["similarity_bp"] = similarity_to_bp(item.get("similarity"))
        item["similarity"] = bp_to_similarity(item["similarity_bp"])
    return ranked


# --------------------------------------------------------------------------
# prompt
# --------------------------------------------------------------------------
ADJUDICATION_OUTPUT_CONTRACT = """{
  "issue": "the question actually decided, in one sentence",
  "facts": ["material fact", "material fact"],
  "verdict": "APPROVED | REJECTED | PARTIAL",
  "ratio": "the reason, in one sentence — the binding part",
  "reason_codes": ["UPPER_SNAKE_CASE"],
  "precedent_used": ["HLD-000184"],
  "followed": true,
  "distinguished": false,
  "distinguishment_reason": "one sentence naming the material difference, or empty string",
  "reasoning": "short explanation of how the precedent was applied or departed from"
}"""

DISTINGUISHING_INSTRUCTION = """PRECEDENT RULE
Consider the retrieved precedent. Follow materially applicable precedent unless
the current facts contain a material distinction.

If you depart from a relevant holding, you must explicitly identify the material
difference in `distinguishment_reason`, set `distinguished` to true, and name the
holding you departed from in `precedent_used`.

A material difference names something concrete about the facts.
REJECTED: "The circumstances differ." / "This case is different."
ACCEPTED: "The previous holding involved a service that had not yet been fully
delivered; this case concerns a service completed before cancellation."

If no precedent was retrieved, decide the case on its own facts and return an
empty `precedent_used` list."""


def format_precedent_block(precedents: Sequence[Dict[str, Any]]) -> str:
    if not precedents:
        return "No precedent was retrieved. The registry has no comparable holding yet."
    lines: List[str] = []
    for item in precedents:
        lines.append(
            "\n".join(
                [
                    f"HOLDING {item.get('holding_id', '')}",
                    f"  domain      : {item.get('domain', '')}",
                    f"  issue       : {item.get('issue', '')}",
                    f"  facts       : {item.get('facts_digest', '')}",
                    f"  verdict     : {item.get('verdict', '')}",
                    f"  ratio       : {item.get('ratio', '')}",
                    f"  similarity  : {bp_to_similarity(similarity_to_bp(item.get('similarity')))}",
                    f"  authority   : {item.get('authority_bp', 0)} bp",
                ]
            )
        )
    return "\n\n".join(lines)


def build_adjudication_prompt(
    case_id: str,
    domain: str,
    facts: Sequence[str],
    precedents: Sequence[Dict[str, Any]],
    question: str = "Decide this case.",
) -> str:
    facts_block = "\n".join(f"- {schema.normalize_text(f)}" for f in facts if str(f).strip())
    return "\n".join(
        [
            question,
            "",
            f"CASE {case_id}",
            f"DOMAIN {schema.normalize_domain(domain)}",
            "",
            "MATERIAL FACTS",
            facts_block or "- (none supplied)",
            "",
            "RETRIEVED PRECEDENT",
            format_precedent_block(precedents),
            "",
            DISTINGUISHING_INSTRUCTION,
            "",
            "Return ONLY a JSON object with this shape, no commentary:",
            ADJUDICATION_OUTPUT_CONTRACT,
        ]
    )


def parse_precedent_used(payload: Dict[str, Any]) -> List[str]:
    raw = payload.get("precedent_used") or []
    if isinstance(raw, str):
        raw = [raw]
    out: List[str] = []
    for item in raw:
        candidate = schema.normalize_text(str(item)).upper()
        if schema.is_valid_holding_id(candidate):
            out.append(candidate)
    return out


def decide_disposition(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Derive FOLLOW / DISTINGUISH from the adjudication output.

    `distinguished` is authoritative when present; otherwise a non-empty
    distinguishment_reason implies departure.
    """
    distinguished_raw = payload.get("distinguished", None)
    reason, reason_errors = None, []
    from .validation import validate_distinguishment  # local import avoids a cycle

    if distinguished_raw is True or (str(distinguished_raw).lower() == "true"):
        reason, reason_errors = validate_distinguishment(
            payload.get("distinguishment_reason"), required=True
        )
        distinguished = True
    else:
        candidate = payload.get("distinguishment_reason")
        reason, reason_errors = validate_distinguishment(candidate)
        distinguished = bool(reason) and not reason_errors

    return {
        "followed": not distinguished,
        "distinguished": distinguished,
        "distinguishment_reason": reason or None,
        "distinguishment_errors": reason_errors,
    }


def precedent_result(holding: Dict[str, Any], similarity: Any, relationship: str) -> Dict[str, Any]:
    bp = similarity_to_bp(similarity)
    return {
        "holding_id": holding.get("holding_id"),
        "similarity": bp_to_similarity(bp),
        "similarity_bp": bp,
        "relationship": relationship,
        "verdict": holding.get("verdict"),
        "issue": holding.get("issue"),
        "authority_bp": holding.get("authority_bp", 0),
        "status": holding.get("status"),
    }
