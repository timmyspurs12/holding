#!/usr/bin/env python3
"""Capture the exact revert reason Bradbury returns for a deploy.

``eth_estimateGas`` collapses every failure into "execution reverted" and throws
the revert data away. This builds the very same transaction, sends it as an
``eth_call`` instead, and prints the raw revert payload plus the decoded error
name. Nothing is ever submitted.

Run it with the key you deploy with:

    export GENLAYER_PRIVATE_KEY="0xYOUR_TESTNET_KEY"
    python scripts/probe_revert.py --network bradbury
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# Keep the SDK importable when this runs from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "services"))

try:
    from dotenv import load_dotenv
except ImportError:  # python-dotenv is optional; exports work fine without it
    load_dotenv = None

# genlayer-py 0.19 maps these; hard-coded so 0.18 works too.
KNOWN_REVERTS = {
    "0x8d53e553": "InsufficientFees",
    "0xb4132db3": "MaxPriceExceeded",
    "0x57df8523": "ExecutionBudgetExceeded",
    "0x305e533c": "BudgetTooLow",
    "0xa70732ee": "RollupBudgetBelowFloor",
    "0x632be5a1": "FeeValueMustBeNonZero",
}

PROBE_SOURCE = (
    "from genlayer import *\n\n"
    "class Probe(gl.Contract):\n"
    "    value: int\n\n"
    "    def __init__(self):\n"
    "        self.value = 7\n"
)

ZERO_FEE_DISTRIBUTION = {
    "leaderTimeunitsAllocation": 0,
    "validatorTimeunitsAllocation": 0,
    "appealRounds": 0,
    "executionBudgetPerRound": 0,
    "executionConsumed": 0,
    "totalMessageFees": 0,
    "rotations": [0],
    "maxPriceGenPerTimeUnit": 1,
    "storageFeeMaxGasPrice": 0,
    "receiptFeeMaxGasPrice": 0,
}

CHAINS = {
    "bradbury": "testnet_bradbury",
    "asimov": "testnet_asimov",
    "studio_devnet": "studio_devnet",
    "studionet": "studionet",
    "localnet": "localnet",
}


def main(argv: list[str] | None = None) -> int:
    if load_dotenv is not None:
        load_dotenv(override=False)

    parser = argparse.ArgumentParser(description="Capture a GenLayer revert reason")
    parser.add_argument("--network", default="bradbury", choices=sorted(CHAINS))
    parser.add_argument("--chain", default="", help="override the chain preset name")
    parser.add_argument("--private-key", default=os.getenv("GENLAYER_PRIVATE_KEY", ""))
    args = parser.parse_args(argv)

    key = (args.private_key or "").strip()
    if not key:
        print("no key: set GENLAYER_PRIVATE_KEY or pass --private-key")
        return 2

    try:
        from genlayer_py import chains, create_client, create_account
    except ImportError:
        print("genlayer-py is not installed: pip install -r requirements-live.txt")
        return 2

    preset = args.chain or CHAINS.get(args.network, args.network)
    chain = getattr(chains, preset, None)
    if chain is None:
        print(f"unknown chain preset: {preset}")
        return 2

    account = create_account(key)
    client = create_client(chain=chain, account=account)
    w3 = client.w3
    sender = w3.to_checksum_address(account.address)

    print(f"network    {preset}")
    print(f"sender     {sender}")
    print(f"balance    {w3.eth.get_balance(sender) / 10 ** 18:.6f} GEN")
    print(f"block      {w3.eth.block_number}")

    # -- build the transaction, but stop before anything is signed or sent ----
    captured: dict = {}
    provider = client.provider
    original = provider.make_request

    def intercept(method, params):
        if method == "eth_estimateGas":
            captured["tx"] = dict(params[0])
            raise RuntimeError("__probe_stop__")
        return original(method, params)

    provider.make_request = intercept
    try:
        client.deploy_contract(
            code=PROBE_SOURCE,
            args=[],
            leader_only=False,
            consensus_max_rotations=3,
            fees={
                "distribution": ZERO_FEE_DISTRIBUTION,
                "feeValue": 0,
                "messageAllocations": [],
            },
        )
    except RuntimeError:
        pass  # the interceptor fired, which is what we wanted
    except Exception as error:  # noqa: BLE001 - validation stopped us early
        if "tx" not in captured:
            print(f"\nstopped before gas estimation: {str(error).splitlines()[0][:160]}")
    finally:
        provider.make_request = original

    tx = captured.get("tx")
    if not tx:
        print("\ncould not capture a transaction, so there is nothing to probe")
        return 1

    print("\n--- eth_call (submits nothing) ---")
    tx.pop("gas", None)
    try:
        result = original("eth_call", params=[tx, "latest"])
        print("accepted:", str(result)[:160])
        print("\nthe node accepts this transaction shape — the failure is elsewhere.")
        return 0
    except Exception as error:  # noqa: BLE001 - the payload is the whole point
        blob = " ".join(
            str(part)
            for part in (
                getattr(error, "data", ""),
                getattr(error, "message", ""),
                getattr(error, "args", ()),
                str(error),
            )
        )
        print("reverted:")
        print(" ", blob[:400])

    names = [name for selector, name in KNOWN_REVERTS.items() if selector in blob]
    if names:
        print(f"\n  >>> REVERT REASON: {', '.join(names)}")
    else:
        print("\n  no known selector matched — pasting the raw payload above into a")
        print("  GenLayer support request will let them identify it immediately.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
