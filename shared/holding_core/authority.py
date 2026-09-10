"""Deterministic authority model.

Nothing here is produced by a model. Every component is derived from an
observable property of the holding, and the arithmetic is integer-only so it can
be recomputed identically inside GenVM and off-chain.

Scale
-----
Components and the final score are integers in basis points (0..10_000).
`score` (0..1) is produced only at the API boundary, for display.

Formula
-------
    authority_bp = sum(component_bp * weight_bp) // 10_000

with weights summing to exactly 10_000. The pure arithmetic lives in
`_mirrored.py` and is reproduced verbatim inside the HoldingRegistry contract.
"""

from __future__ import annotations

from typing import Any, Dict, List

from ._mirrored import (
    APPEAL_BY_OUTCOME,
    BASIS,
    COMPONENT_ORDER,
    FINALITY_BY_STATUS,
    NEUTRAL_CONSISTENCY,
    REFERENCE_PANEL,
    WEIGHTS,
    compute_authority_bp,
    compute_components,
)

EXPLANATIONS: Dict[str, str] = {
    "finality": "whether the originating decision has been attested as finalized",
    "appeal": "what happened during the appeal window",
    "panel": "how many validators produced the decision",
    "citations": "how many later holdings have relied on it",
    "consistency": "how often comparable cases followed rather than departed from it",
}


def compute_authority(
    status: str,
    appeal_outcome: str = "NONE",
    panel_size: int = 0,
    citations: int = 0,
    followed: int = 0,
    distinguished: int = 0,
) -> Dict[str, Any]:
    """Full authority record: score, components, weights and an explanation."""
    components = compute_components(
        status=status,
        appeal_outcome=appeal_outcome,
        panel_size=panel_size,
        citations=citations,
        followed=followed,
        distinguished=distinguished,
    )
    score_bp = compute_authority_bp(components)
    breakdown = [
        {
            "component": name,
            "value_bp": components[name],
            "weight_bp": WEIGHTS[name],
            "contribution_bp": (components[name] * WEIGHTS[name]) // BASIS,
            "meaning": EXPLANATIONS[name],
        }
        for name in COMPONENT_ORDER
    ]
    return {
        "score": round(score_bp / BASIS, 4),
        "score_bp": score_bp,
        "band": band(score_bp),
        "components_bp": components,
        "weights_bp": WEIGHTS,
        "breakdown": breakdown,
        "formula": "authority_bp = sum(component_bp * weight_bp) // 10000",
        "explanation": explain(score_bp, components),
    }


def band(score_bp: int) -> str:
    if score_bp >= 7_500:
        return "HIGH"
    if score_bp >= 4_500:
        return "MODERATE"
    return "DEVELOPING"


def explain(score_bp: int, components: Dict[str, int]) -> str:
    ranked = sorted(components.items(), key=lambda kv: (-kv[1], kv[0]))
    strongest = ranked[0]
    weakest = ranked[-1]
    return (
        f"Authority {score_bp / BASIS:.2f} ({band(score_bp)}). "
        f"Strongest signal: {strongest[0]} at {strongest[1] / BASIS:.2f}. "
        f"Weakest signal: {weakest[0]} at {weakest[1] / BASIS:.2f}. "
        "Every component is derived from an observable property — no model produced this score."
    )


__all__ = [
    "APPEAL_BY_OUTCOME",
    "BASIS",
    "COMPONENT_ORDER",
    "FINALITY_BY_STATUS",
    "NEUTRAL_CONSISTENCY",
    "REFERENCE_PANEL",
    "WEIGHTS",
    "band",
    "compute_authority",
    "compute_authority_bp",
    "compute_components",
    "explain",
]
