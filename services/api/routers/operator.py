"""Operator routes — the wallet-signed half of source registration.

A signed-in address may *propose* a source contract. Only the registry operator
(HOLDING_ADMIN_TOKEN) can approve one, and approval is what calls the contract's
register_source(). That split is the corpus-poisoning defence: signing a message
with a wallet is easy, and it must not by itself let anyone add an emitter to
the canonical registry.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from ...lib.genlayer.config import GenLayerConfig
from ..sources import (
    STATUSES,
    ProposalError,
    SourceContractStore,
    validate_proposal_input,
)
from ..security import idempotency_key
from .auth import require_wallet
from ..wallet import WalletSession

router = APIRouter(prefix="/operator", tags=["operator"])


def _config(request: Request) -> GenLayerConfig:
    return request.app.state.config


def _store(request: Request) -> SourceContractStore:
    return request.app.state.sources


class ProposeRequest(BaseModel):
    contract_address: str = Field(min_length=1, max_length=64)
    domain: str = Field(min_length=1, max_length=64)
    contract_class: str = Field(min_length=1, max_length=64)
    label: str = Field(default="", max_length=80)
    deploy_tx: str = Field(default="", max_length=128)
    notes: str = Field(default="", max_length=500)


@router.get("/source-contracts", summary="Source-contract proposals (public)")
def list_proposals(
    request: Request,
    status_filter: str = Query(default="", alias="status"),
):
    if status_filter and status_filter.upper() not in STATUSES:
        raise HTTPException(
            status_code=422,
            detail=f"status must be one of {', '.join(STATUSES)}",
        )
    store = _store(request)
    items = [item.public() for item in store.list(status=status_filter)]
    counts = {name: len(store.list(status=name)) for name in STATUSES}
    return {
        "network": _config(request).info().model_dump(),
        "total": len(items),
        "counts": counts,
        "items": items,
        "note": (
            "PENDING proposals are requests, not registrations. Only an approved "
            "proposal has been written to the registry contract."
        ),
    }


@router.get("/me", summary="The signed-in address and its proposals")
def me(request: Request, session: WalletSession = Depends(require_wallet)):
    store = _store(request)
    mine = [item.public() for item in store.list(address=session.address)]
    return {
        "network": _config(request).info().model_dump(),
        "session": session.as_dict(),
        "proposals": mine,
        "can_do": [
            "POST /operator/source-contracts",
        ],
        "cannot_do": [
            "approve a proposal (needs HOLDING_ADMIN_TOKEN)",
            "create or attest a holding (needs HOLDING_ADMIN_TOKEN)",
        ],
    }


@router.post(
    "/source-contracts",
    summary="Propose a source contract for registration",
    status_code=status.HTTP_201_CREATED,
)
def propose(
    payload: ProposeRequest,
    request: Request,
    session: WalletSession = Depends(require_wallet),
    idempotency_key_header: Optional[str] = Header(default=None, alias="Idempotency-Key"),
):
    config = _config(request)
    store = _store(request)

    # Replay protection: the same key returns the original proposal.
    if idempotency_key_header:
        cached = request.app.state.idempotency.get("propose", idempotency_key(idempotency_key_header))
        if cached:
            return {**cached, "replayed": True}

    try:
        fields = validate_proposal_input(
            contract_address=payload.contract_address,
            domain=payload.domain,
            contract_class=payload.contract_class,
            label=payload.label,
            deploy_tx=payload.deploy_tx,
            notes=payload.notes,
        )
    except ProposalError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    existing = store.duplicate_of(fields["contract_address"], config)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"a proposal for {fields['contract_address']} already exists "
                f"({existing.proposal_id}, {existing.status})"
            ),
        )

    proposal = store.propose(submitted_by=session.address, simulated=config.simulated, **fields)
    body = {
        "proposal_id": proposal.proposal_id,
        "status": proposal.status,
        "submitted_by": proposal.submitted_by,
        "submitted_at": proposal.submitted_at,
        "contract_address": proposal.contract_address,
        "domain": proposal.domain,
        "contract_class": proposal.contract_class,
        "network": config.info().model_dump(),
        "next": (
            f"An operator approves it with POST /admin/source-contracts/"
            f"{proposal.proposal_id}/approve (HOLDING_ADMIN_TOKEN). "
            "Nothing is registered on-chain until then."
        ),
    }
    if idempotency_key_header:
        request.app.state.idempotency.put("propose", idempotency_key(idempotency_key_header), body)
    return body
