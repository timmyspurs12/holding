"""Network configuration. Secrets come from the environment and are never
logged, serialised into responses, or committed."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional, Tuple

from .types import NETWORK_LABELS, NetworkInfo, NetworkMode

import re

DEMO_REGISTRY = "0xDEMO000000000000000000000000000000000001"
DEMO_ADJUDICATOR = "0xDEMO000000000000000000000000000000000002"

ADDRESS_PATTERN = re.compile(r"^0x[0-9a-fA-F]{40}$")


@dataclass(frozen=True)
class GenLayerConfig:
    mode: NetworkMode
    network: str = "demo"
    rpc_url: str = ""
    chain_id: Optional[int] = None
    registry_address: str = DEMO_REGISTRY
    adjudicator_address: str = DEMO_ADJUDICATOR
    private_key: str = field(default="", repr=False)  # never logged
    admin_token: str = field(default="", repr=False)
    # Wallet sign-in. session_secret is optional: it defaults to a value derived
    # from admin_token (see services/api/wallet.py::session_secret).
    session_secret: str = field(default="", repr=False)
    operator_addresses: Tuple[str, ...] = ()
    # Origin stamped into the sign-in message (behind a proxy the request host
    # is not the public one, so it can be pinned here).
    public_origin: str = ""

    @property
    def simulated(self) -> bool:
        return self.mode is NetworkMode.DEMO

    def info(self) -> NetworkInfo:
        if self.mode is NetworkMode.DEMO:
            return NetworkInfo.demo(self.registry_address, self.adjudicator_address)
        return NetworkInfo(
            mode=self.mode,
            network=self.network,
            chain_id=self.chain_id,
            rpc_url=self.rpc_url,
            registry_address=self.registry_address,
            adjudicator_address=self.adjudicator_address,
            simulated=False,
            note=f"Live {self.network}. Holdings exist only after consensus finality.",
        )

    @classmethod
    def from_env(cls, env=None) -> "GenLayerConfig":
        env = env if env is not None else os.environ
        raw = (env.get("GENLAYER_NETWORK") or "demo").strip().lower()
        mode, network = NETWORK_LABELS.get(raw, (NetworkMode.DEMO, "demo"))

        rpc_url = (env.get("GENLAYER_RPC_URL") or "").strip()
        chain_raw = (env.get("GENLAYER_CHAIN_ID") or "").strip()
        registry = (env.get("HOLDING_REGISTRY_ADDRESS") or "").strip()
        adjudicator = (env.get("ADJUDICATOR_ADDRESS") or "").strip()
        key = (env.get("GENLAYER_PRIVATE_KEY") or "").strip()

        if mode is not NetworkMode.DEMO:
            # A live mode without an address is a misconfiguration, not a
            # silent fallback — we never present demo data as live data.
            if not registry:
                raise ValueError(
                    "HOLDING_REGISTRY_ADDRESS is required when GENLAYER_NETWORK is "
                    f"{raw!r}. Deploy the contract or set GENLAYER_NETWORK=demo."
                )
            if not rpc_url:
                rpc_url = DEFAULT_RPC.get(network, "")
            if not chain_raw:
                chain_raw = str(DEFAULT_CHAIN_ID.get(network, "") or "")

        operators = tuple(
            address.strip().lower()
            for address in (env.get("HOLDING_OPERATOR_ADDRESSES") or "").split(",")
            if address.strip()
        )
        for address in operators:
            if not ADDRESS_PATTERN.match(address):
                raise ValueError(
                    f"HOLDING_OPERATOR_ADDRESSES contains an invalid address: {address!r}"
                )

        return cls(
            mode=mode,
            network=network or "demo",
            rpc_url=rpc_url,
            chain_id=int(chain_raw) if chain_raw.isdigit() else None,
            registry_address=registry or DEMO_REGISTRY,
            adjudicator_address=adjudicator or DEMO_ADJUDICATOR,
            private_key=key,
            admin_token=(env.get("HOLDING_ADMIN_TOKEN") or "").strip(),
            session_secret=(env.get("HOLDING_SESSION_SECRET") or "").strip(),
            operator_addresses=operators,
            public_origin=(env.get("HOLDING_PUBLIC_ORIGIN") or "").strip().rstrip("/"),
        )


# Documented public endpoints (docs.genlayer.com/developers/networks).
DEFAULT_RPC = {
    "testnet_bradbury": "https://rpc-bradbury.genlayer.com",
    "testnet_asimov": "https://rpc-asimov.genlayer.com",
    "studio_devnet": "https://studio-dev.genlayer.com/api",
    "studionet": "https://studio.genlayer.com/api",
    "localnet": "http://127.0.0.1:4000/api",
}

DEFAULT_CHAIN_ID = {
    "testnet_bradbury": 4221,
    "testnet_asimov": 61999,
    "studio_devnet": 61997,
    "studionet": 61999,
    "localnet": 61127,
}
