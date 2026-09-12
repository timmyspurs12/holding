"""Privileged writes.

Three rules shape this router:

1. Nothing is writable without HOLDING_ADMIN_TOKEN (fail closed).
2. Every payload is validated against the same schema the contract enforces, so
   a malformed holding is rejected here before it can reach the registry.
3. Every write needs an Idempotency-Key; a replay returns the original result
   instead of writing twice.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from ...lib.genlayer.base import ContractRejected
from ...lib.genlayer.client import get_registry
from ...lib.genlayer.types import FinalityAttestation
from ..security import idempotency_key, require_admin

def admin_guard(request: Request, x_admin_token: Optional[str] = Header(default=None)) -> None:
    """Runs before body validation: authorization first, parsing second."""
    require_admin(request.app.state.config, x_admin_token)


router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(admin_guard)])

# In DEMO mode writes are sent by the registry owner / attestor; on a live
# network the operator's account signs them.
OWNER = "0x1111111111111111111111111111111111111111"


def _registry(request: Request):
    return get_registry(request.app.state.config)


def _store(request: Request):
    return request.app.state.idempotency


def _guard(request: Request, key: Optional[str], scope: str):
    """Replay protection only — authorization is the router's admin_guard."""
    return _store(request).get(scope, idempotency_key(key))


def _remember(request: Request, scope: str, key: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    _store(request).put(scope, idempotency_key(key), payload)
    return payload


class CreateHoldingRequest(BaseModel):
    case_id: str = Field(min_length=1, max_length=64)
    domain: str = Field(min_length=1, max_length=64)
    contract_class: str = Field(min_length=1, max_length=64)
    issue: str = Field(min_length=8, max_length=512)
    facts_digest: str = Field(min_length=8, max_length=1024)
    verdict: str
    ratio: str = Field(min_length=20, max_length=2048)
    reason_codes: List[str] = Field(default_factory=list)
    evidence_hashes: List[str] = Field(default_factory=list)
    panel_size: int = Field(default=1, ge=1, le=128)
    source_tx: str = ""
    appeal_status: str = "NONE"
    appeal_outcome: str = "NONE"
    distinguishment: str = ""
    sender: str = OWNER


class FinalityRequest(FinalityAttestation):
    sender: str = OWNER


class CitationRequest(BaseModel):
    source_holding_id: str
    target_holding_id: str
    relationship: str
    case_id: str = ""
    sender: str = OWNER


class RejectRequest(BaseModel):
    reason: str = Field(min_length=8, max_length=1024)
    sender: str = OWNER


@router.post("/holdings", summary="Create an unverified record")
def create_holding(
    payload: CreateHoldingRequest,
    request: Request,
    idempotency_key_header: Optional[str] = Header(default=None, alias="Idempotency-Key"),
):
    cached = _guard(request, idempotency_key_header, "create_holding")
    if cached:
        return {**cached, "replayed": True}

    from shared.holding_core import validation

    data = payload.model_dump()
    sender = data.pop("sender")
    appeal_status = data.pop("appeal_status", "NONE")
    appeal_outcome = data.pop("appeal_outcome", "NONE")
    distinguishment = data.pop("distinguishment", "")
    try:
        validated = validation.validate_holding_creation(**data)
    except validation.ValidationError as error:
        raise HTTPException(status_code=422, detail="invalid request payload") from error

    registry = _registry(request)
    try:
        result = registry.create_holding(
            **validated,
            appeal_status=appeal_status,
            appeal_outcome=appeal_outcome,
            distinguishment=distinguishment,
            sender=sender,
        )
    except ContractRejected as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    return _remember(
        request,
        "create_holding",
        idempotency_key_header or "",
        {
            "status": "UNVERIFIED",
            "method": "create_holding",
            "transaction_reference": result.transaction_reference,
            "simulated": result.simulated,
            "payload": validated,
        },
    )


@router.post("/holdings/{holding_id}/finality", summary="Attest finality (UNVERIFIED RECORD -> FINAL HOLDING)")
def attest_finality(
    holding_id: str,
    payload: FinalityRequest,
    request: Request,
    idempotency_key_header: Optional[str] = Header(default=None, alias="Idempotency-Key"),
):
    cached = _guard(request, idempotency_key_header, f"attest:{holding_id}")
    if cached:
        return {**cached, "replayed": True}

    registry = _registry(request)
    result = registry.attest_finality(
        holding_id=holding_id,
        tx_status_code=payload.tx_status_code,
        execution_result=payload.execution_result,
        finality_timestamp=payload.finality_timestamp,
        appeal_outcome=payload.appeal_outcome,
        source_tx=payload.source_tx,
        sender=payload.sender,
    )
    holding = registry.get_holding(holding_id)
    return _remember(
        request,
        f"attest:{holding_id}",
        idempotency_key_header or "",
        {
            "holding_id": holding_id,
            "status": holding.status if holding else "UNKNOWN",
            "settles": payload.settles,
            "transaction_reference": result.transaction_reference,
            "simulated": result.simulated,
        },
    )


@router.post("/citations", summary="Record CITES / FOLLOWS / DISTINGUISHES")
def create_citation(
    payload: CitationRequest,
    request: Request,
    idempotency_key_header: Optional[str] = Header(default=None, alias="Idempotency-Key"),
):
    cached = _guard(request, idempotency_key_header, "cite")
    if cached:
        return {**cached, "replayed": True}

    from shared.holding_core import schema, validation

    registry = _registry(request)
    known = [h.holding_id for h in registry.list_holdings(limit=10_000)]
    errors = validation.validate_relationship(
        payload.source_holding_id, payload.target_holding_id, payload.relationship, known
    )
    if errors:
        raise HTTPException(status_code=422, detail="; ".join(errors))

    result = registry.cite(
        source_holding_id=payload.source_holding_id,
        target_holding_id=payload.target_holding_id,
        relationship=payload.relationship,
        case_id=payload.case_id,
        sender=payload.sender,
    )
    return _remember(
        request,
        "cite",
        idempotency_key_header or "",
        {
            "recorded": bool(result.result),
            "relationship": payload.relationship.upper(),
            "transaction_reference": result.transaction_reference,
            "simulated": result.simulated,
        },
    )


@router.post("/holdings/{holding_id}/reject", summary="Mark a record as not eligible to be precedent")
def reject_holding(
    holding_id: str,
    payload: RejectRequest,
    request: Request,
    idempotency_key_header: Optional[str] = Header(default=None, alias="Idempotency-Key"),
):
    cached = _guard(request, idempotency_key_header, f"reject:{holding_id}")
    if cached:
        return {**cached, "replayed": True}

    registry = _registry(request)
    result = registry.reject_holding(holding_id=holding_id, reason=payload.reason, sender=payload.sender)
    return _remember(
        request,
        f"reject:{holding_id}",
        idempotency_key_header or "",
        {
            "holding_id": holding_id,
            "status": "REJECTED",
            "transaction_reference": result.transaction_reference,
            "simulated": result.simulated,
        },
    )


# ---------------------------------------------------------------------------
# Source-contract proposals
#
# The wallet half of registration lives in /operator; a wallet can only
# propose. Approving is what calls register_source() on the contract, so it
# stays behind HOLDING_ADMIN_TOKEN.
# ---------------------------------------------------------------------------


class DecisionRequest(BaseModel):
    note: str = Field(default="", max_length=500)


def _decide(request: Request, proposal_id: str, approve: bool, payload: DecisionRequest):
    from ..sources import APPROVED, REJECTED, ProposalError

    store = request.app.state.sources
    proposal = store.get(proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail=f"unknown proposal {proposal_id}")

    transaction_reference = None
    registered_on_chain = False
    contract_error = None

    if approve:
        registry = _registry(request)
        try:
            result = registry.register_source(address=proposal.contract_address, allowed=True, sender=OWNER)
            transaction_reference = result.transaction_reference
        except ContractRejected as error:
            contract_error = str(error)
        except Exception as error:  # pragma: no cover - depends on the network
            contract_error = str(error)
        else:
            registered_on_chain = registry.is_registered_source(proposal.contract_address)

    try:
        decided = store.decide(
            proposal_id,
            status=APPROVED if (approve and contract_error is None) else REJECTED,
            decided_by="admin",
            note=payload.note or (contract_error or ""),
            transaction_reference=transaction_reference,
        )
    except ProposalError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error

    body = {
        "proposal_id": proposal_id,
        "status": decided.status,
        "contract_address": decided.contract_address,
        "domain": decided.domain,
        "contract_class": decided.contract_class,
        "submitted_by": decided.submitted_by,
        "decided_at": decided.decided_at,
        "decision_note": decided.decision_note,
        "transaction_reference": decided.transaction_reference,
        "registered_on_chain": registered_on_chain,
        "simulated": decided.simulated,
        "network": request.app.state.config.info().model_dump(),
    }
    if contract_error:
        body["contract_error"] = contract_error
        body["status"] = REJECTED
        body["note"] = "the contract refused the registration; the proposal stays decided as REJECTED"
    return body


@router.post("/source-contracts/{proposal_id}/approve", summary="Approve a proposal and register the source on-chain")
def approve_source(
    proposal_id: str,
    payload: DecisionRequest,
    request: Request,
    idempotency_key_header: Optional[str] = Header(default=None, alias="Idempotency-Key"),
):
    cached = _guard(request, idempotency_key_header, f"approve:{proposal_id}")
    if cached:
        return {**cached, "replayed": True}
    body = _decide(request, proposal_id, True, payload)
    return _remember(request, f"approve:{proposal_id}", idempotency_key_header or "", body)


@router.post("/source-contracts/{proposal_id}/reject", summary="Decline a proposal")
def reject_source(
    proposal_id: str,
    payload: DecisionRequest,
    request: Request,
    idempotency_key_header: Optional[str] = Header(default=None, alias="Idempotency-Key"),
):
    cached = _guard(request, idempotency_key_header, f"reject:{proposal_id}")
    if cached:
        return {**cached, "replayed": True}
    body = _decide(request, proposal_id, False, payload)
    return _remember(request, f"reject:{proposal_id}", idempotency_key_header or "", body)
