"""Case simulation — clearly labelled, never presented as history.

Reachable in DEMO mode, and on a testnet only when HOLDING_ALLOW_SIMULATION is
explicitly enabled. Everything returned here carries `simulated: true`, the
network block says DEMO, and the records are marked as simulated cases rather
than historical GenLayer adjudications.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from ...lib.genlayer.base import ContractRejected
from ...lib.genlayer.client import get_chain, get_registry
from ...lib.genlayer.types import NetworkMode
from ..security import require_admin

router = APIRouter(prefix="/demo", tags=["simulation"])

# The canonical six-step loop, in the order the brief specifies.
SEED_CASES: List[Dict[str, Any]] = [
    {
        "case_id": "CASE-001",
        "facts": [
            "Digital service purchased 14 days before cancellation",
            "Approximately 40% of the entitlement consumed",
            "No usage-based exclusion in the purchase terms",
        ],
    },
    {
        "case_id": "CASE-002",
        "facts": [
            "Monthly recurring plan, cancelled 14 days into the billing cycle",
            "Approximately 40% of the cycle entitlement consumed",
            "No usage-based exclusion in the plan terms",
        ],
    },
    {
        "case_id": "CASE-003",
        "facts": [
            "Digital service purchased 12 days before cancellation",
            "The service was fully delivered before cancellation",
            "No usage-based exclusion in the purchase terms",
        ],
    },
]


class CaseRequest(BaseModel):
    case_id: str = Field(min_length=1, max_length=64)
    facts: List[str] = Field(default_factory=list, min_length=1, max_length=20)
    settle: bool = True


def _guard(request: Request, token: Optional[str] = None) -> None:
    config = request.app.state.config
    if config.mode is NetworkMode.MAINNET:
        raise HTTPException(status_code=403, detail="case simulation is disabled on mainnet")
    if config.mode is NetworkMode.TESTNET:
        if os.getenv("HOLDING_ALLOW_SIMULATION", "").lower() not in ("1", "true", "yes"):
            raise HTTPException(
                status_code=403,
                detail="case simulation on a testnet requires HOLDING_ALLOW_SIMULATION=true",
            )
        # writing to a live network, even a testnet, is an operator action
        require_admin(config, token)


def run_case(request: Request, case_id: str, facts: List[str], settle: bool = True) -> Dict[str, Any]:
    registry = get_registry(request.app.state.config)
    chain = get_chain(request.app.state.config)
    sender = registry.adjudicator_address

    facts = [" ".join(str(fact).split()).strip() for fact in facts if str(fact).strip()]
    if not facts:
        raise HTTPException(status_code=422, detail="at least one material fact is required")

    try:
        submitted = registry.submit_case(case_id, facts, sender=sender)
        adjudicated = registry.adjudicate(case_id, sender=sender)
    except ContractRejected as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    receipts: List[Dict[str, Any]] = []
    if settle:
        receipts = [receipt.model_dump() for receipt in chain.settle(adjudicated.transaction_reference)]

    case = registry.get_case(case_id)
    holding = registry.get_holding(case.holding_id) if (case and case.holding_id) else None

    return {
        "simulated": True,
        "warning": (
            "SIMULATED CASE — executed by the DEMO adapter against the real contract "
            "logic. It is not a historical GenLayer adjudication."
        ),
        "case": case.model_dump() if case else {"case_id": case_id},
        "holding": holding.model_dump() if holding else None,
        "precedent_retrieved": [
            hit.model_dump()
            for hit in registry.get_precedent(" ".join(facts), case.domain if case else "", 3)
        ],
        "transactions": {
            "submit_case": submitted.transaction_reference,
            "adjudicate": adjudicated.transaction_reference,
            "receipts": receipts,
        },
    }


@router.post("/cases", summary="Run one simulated case through the contract")
def simulate_case(payload: CaseRequest, request: Request, x_admin_token: Optional[str] = Header(default=None)):
    _guard(request, x_admin_token)
    return run_case(request, payload.case_id, payload.facts, payload.settle)


@router.post("/seed", summary="Run the canonical loop: #001 -> FOLLOWS -> #002 -> DISTINGUISHES #001 -> #003")
def seed(request: Request, x_admin_token: Optional[str] = Header(default=None)):
    _guard(request, x_admin_token)
    steps = []
    for case in SEED_CASES:
        steps.append(run_case(request, case["case_id"], case["facts"], settle=True))
    registry = get_registry(request.app.state.config)
    return {
        "simulated": True,
        "network": request.app.state.config.info().model_dump(),
        "steps": steps,
        "holdings": [holding.model_dump() for holding in registry.list_holdings(limit=100)],
        "stats": registry.stats().model_dump(),
    }
