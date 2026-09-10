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

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from ...lib.genlayer.base import ContractRejected
from ...lib.genlayer.client import get_registry
from ...lib.genlayer.types import FinalityAttestation
from ..security import idempotency_key, require_admin

router = APIRouter(prefix="/admin", tags=["admin"])

# In DEMO mode writes are sent by the registry owner / attestor; on a live
# network the operator's account signs them.
OWNER = "0x1111111111111111111111111111111111111111"


def _registry(request: Request):
    return get_registry(request.app.state.config)


def _store(request: Request):
    return request.app.state.idempotency


def _guard(request: Request, token: Optional[str], key: Optional[str], scope: str):
    require_admin(request.app.state.config, token)
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
    x_admin_token: Optional[str] = Header(default=None),
    idempotency_key_header: Optional[str] = Header(default=None, alias="Idempotency-Key"),
):
    cached = _guard(request, x_admin_token, idempotency_key_header, "create_holding")
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
    x_admin_token: Optional[str] = Header(default=None),
    idempotency_key_header: Optional[str] = Header(default=None, alias="Idempotency-Key"),
):
    cached = _guard(request, x_admin_token, idempotency_key_header, f"attest:{holding_id}")
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
    x_admin_token: Optional[str] = Header(default=None),
    idempotency_key_header: Optional[str] = Header(default=None, alias="Idempotency-Key"),
):
    cached = _guard(request, x_admin_token, idempotency_key_header, "cite")
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
    x_admin_token: Optional[str] = Header(default=None),
    idempotency_key_header: Optional[str] = Header(default=None, alias="Idempotency-Key"),
):
    cached = _guard(request, x_admin_token, idempotency_key_header, f"reject:{holding_id}")
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
