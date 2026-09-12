"""Wallet sign-in: prove control of an address, get a short-lived session.

Three endpoints, no accounts:

    GET  /auth/config   what to sign, which chain, whether sign-in is available
    GET  /auth/nonce    issue a single-use nonce + the exact message to sign
    POST /auth/verify   check the signature, return a session token

The session authorises exactly one thing: submitting source-contract
registration proposals under the address that signed. It does not authorise
registry writes — those still need HOLDING_ADMIN_TOKEN, and approving a
proposal (the step that actually calls the contract) needs it too.
"""

from __future__ import annotations

import time
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from ...lib.genlayer.config import GenLayerConfig
from ..wallet import (
    NONCE_TTL_SECONDS,
    SESSION_TTL_SECONDS,
    STATEMENT,
    NonceStore,
    WalletSession,
    build_message,
    is_operator,
    issue_session,
    normalize_address,
    read_session,
    recover_signer,
    session_secret,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _config(request: Request) -> GenLayerConfig:
    return request.app.state.config


def _nonces(request: Request) -> NonceStore:
    return request.app.state.nonces


def _origin(request: Request, config: GenLayerConfig) -> str:
    """The origin stamped into the signed message.

    Pinned by HOLDING_PUBLIC_ORIGIN when the Reporter sits behind a proxy,
    otherwise the request's own base URL.
    """
    return config.public_origin or str(request.base_url).rstrip("/")


def _chain_id(config: GenLayerConfig) -> int:
    return int(config.chain_id or 0)


def _require_secret(config: GenLayerConfig) -> str:
    secret = session_secret(config)
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "wallet sign-in is disabled: set HOLDING_SESSION_SECRET, or "
                "HOLDING_ADMIN_TOKEN (a session key is derived from it)"
            ),
        )
    return secret


def _require_signer() -> None:
    try:
        from eth_account import Account  # noqa: F401
    except ImportError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="wallet sign-in is unavailable: eth-account is not installed",
        ) from error


# -- the dependency operator routes use --------------------------------


def require_wallet(
    request: Request,
    x_session_token: Optional[str] = Header(default=None, alias="X-Session-Token"),
    authorization: Optional[str] = Header(default=None),
) -> WalletSession:
    """Accept a session token from X-Session-Token or Authorization: Bearer."""
    config = _config(request)
    secret = _require_secret(config)

    token = (x_session_token or "").strip()
    if not token and authorization:
        scheme, _, value = authorization.partition(" ")
        if scheme.lower() == "bearer":
            token = value.strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="wallet sign-in required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    address = read_session(secret, token)
    if address is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid or expired wallet session",
            headers={"WWW-Authenticate": "Bearer"},
        )

    _, _, _, expires_at = _split_token(token)
    return WalletSession(
        address=address,
        expires_at=expires_at,
        is_operator=is_operator(config, address),
        operator_allowlist=bool(config.operator_addresses),
    )


def require_operator(session: WalletSession = Depends(require_wallet)) -> WalletSession:
    """A signed-in address that is also on the operator allowlist."""
    if not session.is_operator:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="this address is not on HOLDING_OPERATOR_ADDRESSES",
        )
    return session


def _split_token(token: str):
    parts = token.split(".")
    if len(parts) != 4:
        return None, None, None, 0
    return parts[0], parts[1], parts[2], int(parts[1]) if parts[1].isdigit() else 0


# -- routes -------------------------------------------------------------


@router.get("/config", summary="What the wallet has to sign, and whether sign-in is on")
def auth_config(request: Request):
    config = _config(request)
    try:
        _require_signer()
        signer_available = True
    except HTTPException:
        signer_available = False
    return {
        "wallet_auth": {
            "available": signer_available and bool(session_secret(config)),
            "signer_available": signer_available,
            "secret_configured": bool(session_secret(config)),
            "statement": STATEMENT,
            "nonce_ttl_seconds": NONCE_TTL_SECONDS,
            "session_ttl_seconds": SESSION_TTL_SECONDS,
        },
        "expected": {
            "origin": _origin(request, config),
            "chain_id": _chain_id(config),
            "chain_id_hex": hex(_chain_id(config)) if _chain_id(config) else None,
            "network": config.network,
            "mode": config.mode.value,
        },
        "operator_allowlist": {
            "configured": bool(config.operator_addresses),
            "count": len(config.operator_addresses),
        },
        "note": (
            "Signing is free and off-chain. A session lets an address submit "
            "source-contract proposals; it never writes to the registry."
        ),
    }


@router.get("/nonce", summary="Issue a single-use sign-in nonce")
def issue_nonce(address: str, request: Request):
    config = _config(request)
    _require_signer()
    try:
        normalized = normalize_address(address)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    store = _nonces(request)
    try:
        nonce, issued_at = store.issue(normalized, _origin(request, config), _chain_id(config))
    except RuntimeError as error:  # pragma: no cover - needs 5k concurrent nonces
        raise HTTPException(status_code=429, detail=str(error)) from error

    message = build_message(
        uri=_origin(request, config),
        address=normalized,
        nonce=nonce,
        issued_at=issued_at,
        chain_id=_chain_id(config),
    )
    return {
        "address": normalized,
        "nonce": nonce,
        "message": message,
        "chain_id": _chain_id(config),
        "issued_at": issued_at,
        "expires_at": issued_at + NONCE_TTL_SECONDS,
    }


class VerifyRequest(BaseModel):
    address: str = Field(min_length=1, max_length=64)
    nonce: str = Field(min_length=1, max_length=128)
    signature: str = Field(min_length=1, max_length=512)
    # The client may send the message it signed; we ignore it and rebuild
    # the text from the stored nonce record.
    message: str = Field(default="", max_length=4096)


@router.post("/verify", summary="Verify a signature and open a session")
def verify_signature(payload: VerifyRequest, request: Request):
    config = _config(request)
    _require_signer()
    secret = _require_secret(config)

    try:
        normalized = normalize_address(payload.address)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    # Single use: a second attempt with the same nonce finds nothing.
    record = _nonces(request).consume(payload.nonce, normalized)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="unknown, expired, or already-used nonce",
        )

    # Rebuilt from what we stored, never from what the client sent.
    message = build_message(
        uri=record.uri,
        address=record.address,
        nonce=payload.nonce,
        issued_at=record.issued_at,
        chain_id=record.chain_id,
    )
    signer = recover_signer(message, payload.signature)
    if signer is None or signer != normalized:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="signature does not match this address",
        )

    token, expires_at = issue_session(secret, normalized)
    session = WalletSession(
        address=normalized,
        expires_at=expires_at,
        is_operator=is_operator(config, normalized),
        operator_allowlist=bool(config.operator_addresses),
    )
    return {
        "token": token,
        "token_type": "Bearer",
        "header": "X-Session-Token",
        "session": session.as_dict(),
        "network": {"mode": config.mode.value, "network": config.network, "chain_id": _chain_id(config)},
        "grants": [
            "POST /operator/source-contracts",
            "GET /operator/me",
        ],
        "note": (
            "This session cannot write to the registry. Proposals are approved "
            "separately with HOLDING_ADMIN_TOKEN."
        ),
    }


@router.get("/session", summary="Is this session still valid?")
def current_session(request: Request, session: WalletSession = Depends(require_wallet)):
    config = _config(request)
    payload = session.as_dict()
    payload["network"] = {"mode": config.mode.value, "chain_id": _chain_id(config)}
    payload["seconds_remaining"] = max(0, session.expires_at - int(time.time()))
    return payload
