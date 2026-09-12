"""Wallet-signed operator sessions.

Why this exists
---------------
Registering a source contract on HOLDING is a privileged act: a registered
source is allowed to emit holdings into the canonical registry. Handing that
out to anyone who can paste an admin token into a browser is how a precedent
corpus gets poisoned. So the flow is split in two:

  1. A wallet proves control of an address by signing a nonce        (this file)
  2. That address *proposes* a source contract; the operator *approves* it,
     and only the approval calls the contract's register_source()

The wallet never writes to the registry on its own. A verified session can
submit a proposal and read its own proposals; nothing else.

What a wallet session is NOT
----------------------------
* It is not a transaction. The signature is an off-chain `personal_sign`
  message, so it costs nothing and cannot move funds.
* It is not an account. There are no passwords, no e-mail, no OAuth, no
  database of users. The nonce store and the session are the whole thing.
* It is not required to read anything. Every read endpoint stays open; the
  Reporter is a public record.

Replay protection
-----------------
A nonce is single-use, expires after five minutes, and is bound to one
address, one origin and one chain id. The message that gets verified is
rebuilt server-side from the stored record — the client's copy of the text is
never trusted — so a caller cannot widen the statement it signed.

Dependencies
------------
Signature recovery needs `eth-account`. If it is missing the auth routes
return 503 rather than silently accepting or silently failing open.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from ..lib.genlayer.config import GenLayerConfig

NONCE_TTL_SECONDS = 300
SESSION_TTL_SECONDS = 8 * 3600
MAX_PENDING_NONCES = 5_000

STATEMENT = (
    "Sign in to HOLDING as an operator. This links your address to "
    "source-contract registration requests. It is not a transaction and it "
    "cannot move funds."
)

ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")


class WalletAuthUnavailable(RuntimeError):
    """Raised when signature verification cannot be performed at all."""


def normalize_address(value: str) -> str:
    """Validate an EVM address and return it lower-cased.

    Lower-casing is deliberate: the registry compares addresses as strings, and
    a mixed-case address that means the same key must not read as a different
    operator.
    """
    address = (value or "").strip()
    if not ADDRESS_RE.match(address):
        raise ValueError("not a valid EVM address")
    return address.lower()


def is_valid_address(value: str) -> bool:
    try:
        normalize_address(value)
        return True
    except ValueError:
        return False


def short_address(address: str) -> str:
    return f"{address[:6]}…{address[-4:]}" if len(address) == 42 else address


# -- the signing payload ------------------------------------------------


def build_message(
    *,
    uri: str,
    address: str,
    nonce: str,
    issued_at: int,
    chain_id: int,
) -> str:
    """The exact text a wallet signs.

    Every field here is echoed back into the message so the person signing can
    read what they are agreeing to, and so the server can rebuild this string
    byte-for-byte at verification time from the stored nonce record.
    """
    issued = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(issued_at))
    chain = str(chain_id) if chain_id else "none (DEMO — there is no chain to sign against)"
    return (
        f"{uri} wants you to sign in with your GenLayer account:\n"
        f"{address}\n"
        f"\n"
        f"{STATEMENT}\n"
        f"\n"
        f"URI: {uri}\n"
        f"Version: 1\n"
        f"Chain ID: {chain}\n"
        f"Nonce: {nonce}\n"
        f"Issued At: {issued}"
    )


# -- nonce store --------------------------------------------------------


@dataclass(frozen=True)
class NonceRecord:
    address: str
    uri: str
    chain_id: int
    issued_at: int


class NonceStore:
    """Single-use, expiring, address-bound nonces. In-process."""

    def __init__(self, ttl_seconds: int = NONCE_TTL_SECONDS) -> None:
        self.ttl = ttl_seconds
        self._records: Dict[str, NonceRecord] = {}
        self._lock = threading.Lock()

    def issue(self, address: str, uri: str, chain_id: int, now: Optional[float] = None) -> Tuple[str, int]:
        now = now if now is not None else time.time()
        with self._lock:
            self._sweep(now)
            if len(self._records) >= MAX_PENDING_NONCES:
                raise RuntimeError("too many pending sign-in requests")
            nonce = secrets.token_hex(16)
            self._records[nonce] = NonceRecord(address=address, uri=uri, chain_id=chain_id, issued_at=int(now))
        return nonce, int(now)

    def consume(self, nonce: str, address: str, now: Optional[float] = None) -> Optional[NonceRecord]:
        """Return the record once, then forget it. None if unknown/expired/wrong address."""
        now = now if now is not None else time.time()
        with self._lock:
            record = self._records.pop(nonce, None)
        if record is None:
            return None
        if now - record.issued_at > self.ttl:
            return None
        if record.address != address:
            return None
        return record

    def _sweep(self, now: float) -> None:
        for nonce, record in list(self._records.items()):
            if now - record.issued_at > self.ttl:
                self._records.pop(nonce, None)

    def pending(self) -> int:
        with self._lock:
            return len(self._records)


# -- signature recovery -------------------------------------------------


def _eth_account():
    try:
        from eth_account import Account  # type: ignore
        from eth_account.messages import encode_defunct  # type: ignore

        return Account, encode_defunct
    except ImportError as error:  # pragma: no cover - depends on the environment
        raise WalletAuthUnavailable(
            "wallet sign-in is unavailable: eth-account is not installed "
            "(pip install -r requirements.txt)"
        ) from error


def recover_signer(message: str, signature: str) -> Optional[str]:
    """Recover the address that signed `message`. None if the signature is junk."""
    Account, encode_defunct = _eth_account()
    raw = (signature or "").strip()
    if not raw:
        return None
    if not raw.startswith("0x"):
        raw = "0x" + raw
    try:
        signer = Account.recover_message(encode_defunct(text=message), signature=raw)
    except Exception:  # noqa: BLE001 - malformed signatures surface as bad input
        return None
    return str(signer).lower()


# -- sessions -----------------------------------------------------------


def session_secret(config: GenLayerConfig) -> str:
    """The HMAC key for session tokens.

    HOLDING_SESSION_SECRET if set, otherwise derived from HOLDING_ADMIN_TOKEN so
    a default install works with no extra configuration. Rotating the admin
    token therefore invalidates every session — set the dedicated secret if you
    do not want that coupling.
    """
    if config.session_secret:
        return config.session_secret
    if config.admin_token:
        return hashlib.sha256(b"holding/session/v1|" + config.admin_token.encode("utf-8")).hexdigest()
    return ""


def issue_session(secret: str, address: str, now: Optional[float] = None, ttl: int = SESSION_TTL_SECONDS) -> Tuple[str, int]:
    now = now if now is not None else time.time()
    expires_at = int(now) + int(ttl)
    body = f"v1.{expires_at}.{address}"
    mac = hmac.new(secret.encode("utf-8"), body.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{body}.{mac}", expires_at


def read_session(secret: str, token: str, now: Optional[float] = None) -> Optional[str]:
    """Return the session's address, or None if the token is forged or expired."""
    if not secret or not token:
        return None
    parts = token.split(".")
    if len(parts) != 4 or parts[0] != "v1":
        return None
    _, expires_raw, address, mac = parts
    body = f"v1.{expires_raw}.{address}"
    expected = hmac.new(secret.encode("utf-8"), body.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, mac):
        return None
    try:
        expires_at = int(expires_raw)
    except ValueError:
        return None
    now = now if now is not None else time.time()
    if now >= expires_at:
        return None
    if not is_valid_address(address):
        return None
    return address


@dataclass(frozen=True)
class WalletSession:
    address: str
    expires_at: int
    is_operator: bool
    operator_allowlist: bool

    def as_dict(self) -> Dict[str, object]:
        return {
            "address": self.address,
            "short_address": short_address(self.address),
            "expires_at": self.expires_at,
            "is_operator": self.is_operator,
            "operator_allowlist": self.operator_allowlist,
        }


def is_operator(config: GenLayerConfig, address: str) -> bool:
    """True only when an allowlist exists and contains this address.

    With no allowlist configured nobody is an operator — an unset list must not
    read as "everybody".
    """
    return bool(config.operator_addresses) and address.lower() in config.operator_addresses
