#!/usr/bin/env python3
"""Diagnose a GenLayer network before you try to deploy.

Run this when `deploy_contracts.py` fails with "execution reverted". That error
is what the node returns for several very different problems — an empty wallet,
a stale consensus address in the SDK, or the wrong RPC — and the message itself
does not say which.

    python scripts/diagnose_network.py --network bradbury

Every check is independent: one failure never hides the others.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def load_env() -> None:
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    path = ROOT / ".env"
    if path.exists():
        load_dotenv(path, override=False)


def section(title: str) -> None:
    print(f"\n{title}\n{'-' * len(title)}")


def scan_consensus_health(client, blocks: int, deadline: float = 60.0):
    """Report recent consensus activity, using logs rather than a block walk.

    Walking blocks one by one takes minutes on a quiet network and looks frozen.
    ``eth_getLogs`` answers in a single RPC call. Caveat that must be stated in
    the output: a reverted transaction emits no events, so this counts
    *successful* consensus activity only - it cannot measure a failure rate.

    Returns (found, succeeded, failed, timed_out).
    """
    started = time.time()
    w3 = client.w3
    consensus = w3.to_checksum_address(client.chain.consensus_main_contract["address"])
    head = w3.eth.block_number

    logs = w3.eth.get_logs(
        {"address": consensus, "fromBlock": max(0, head - blocks), "toBlock": head}
    )
    hashes = sorted({log["transactionHash"] for log in logs}, key=lambda h: h.hex())

    succeeded = failed = 0
    timed_out = False
    for tx_hash in hashes[:25]:
        if time.time() - started > deadline:
            timed_out = True
            break
        try:
            status = w3.eth.get_transaction_receipt(tx_hash).get("status")
        except Exception:  # noqa: BLE001
            status = None
        if status == 1:
            succeeded += 1
        else:
            failed += 1
    return len(hashes), succeeded, failed, timed_out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Diagnose a GenLayer network connection")
    parser.add_argument(
        "--network",
        default="bradbury",
        choices=["bradbury", "asimov", "studio_devnet", "studionet", "localnet"],
    )
    parser.add_argument("--endpoint", default=os.getenv("GENLAYER_RPC_URL", ""))
    parser.add_argument("--private-key", default=os.getenv("GENLAYER_PRIVATE_KEY", ""))
    parser.add_argument(
        "--health-blocks",
        type=int,
        default=int(os.getenv("HOLDING_HEALTH_BLOCKS", "800")),
        help="how many recent blocks to scan for the network health check; stops early once 15 transactions are found (0 skips it)",
    )
    args = parser.parse_args(argv)
    load_env()
    if not args.private_key:
        args.private_key = os.getenv("GENLAYER_PRIVATE_KEY", "")

    print(f"HOLDING network check · {args.network}")

    # -- 1 · SDK -------------------------------------------------------
    section("SDK")
    try:
        from importlib.metadata import version

        print(f"  genlayer-py            {version('genlayer-py')}")
    except Exception as error:  # noqa: BLE001
        print(f"  genlayer-py            unknown ({error})")

    try:
        from genlayer_py import chains, create_account, create_client
    except ImportError:
        print("  genlayer-py is not installed. Run: pip install -r requirements-live.txt")
        return 1

    # -- 2 · chain preset ----------------------------------------------
    section("Chain preset")
    name = {
        "bradbury": "testnet_bradbury",
        "asimov": "testnet_asimov",
        "studio_devnet": "studio_devnet",
    }.get(args.network, args.network)
    chain = getattr(chains, name, None)
    if chain is None:
        print(f"  no preset named {name!r}")
        print(f"  available: {', '.join(n for n in dir(chains) if not n.startswith('_'))}")
        return 1
    consensus = (chain.consensus_main_contract or {}).get("address", "")
    rpc = args.endpoint or list(chain.rpc_urls["default"]["http"])[0]
    print(f"  name                   {chain.name}")
    print(f"  chain id               {chain.id}")
    print(f"  rpc                    {rpc}")
    print(f"  consensus contract     {consensus}")
    print(f"  initial validators     {chain.default_number_of_initial_validators}")
    print(f"  max rotations          {chain.default_consensus_max_rotations}")

    # -- 3 · account ----------------------------------------------------
    section("Account")
    if not args.private_key:
        print("  GENLAYER_PRIVATE_KEY is not set — export it or put it in .env")
        return 1
    try:
        account = create_account(args.private_key)
    except Exception as error:  # noqa: BLE001
        print(f"  the key did not load: {error}")
        return 1
    print(f"  address                {account.address}")

    # -- 4 · client ------------------------------------------------------
    try:
        client = create_client(chain=chain, endpoint=args.endpoint or None, account=account)
    except Exception as error:  # noqa: BLE001
        print(f"\n  could not build a client: {error}")
        return 1

    problems: list[str] = []

    # -- 5 · is the RPC alive? -------------------------------------------
    section("Node")
    try:
        node_chain_id = client.w3.eth.chain_id
        print(f"  chain id               {node_chain_id}")
        if int(node_chain_id) != int(chain.id):
            problems.append(
                f"the node reports chain {node_chain_id} but the SDK preset expects {chain.id} — wrong RPC"
            )
    except Exception as error:  # noqa: BLE001
        print(f"  unreachable: {error}")
        problems.append("the RPC did not answer — check GENLAYER_RPC_URL and your connection")
        node_chain_id = None

    try:
        print(f"  block number           {client.w3.eth.block_number}")
    except Exception as error:  # noqa: BLE001
        print(f"  block number           unavailable ({error})")

    # -- 6 · is the consensus contract actually there? -------------------
    if consensus:
        try:
            code = client.w3.eth.get_code(consensus)
            deployed = bool(code and len(code) > 2)
            print(f"  consensus contract     {'present' if deployed else 'MISSING (no code at this address)'}")
            if not deployed:
                problems.append(
                    "the SDK's consensus address has no contract on this network — the preset is stale. "
                    "Upgrade genlayer-py, or point GENLAYER_RPC_URL at the network this preset belongs to."
                )
        except Exception as error:  # noqa: BLE001
            print(f"  consensus contract     could not read ({error})")

    # -- 7 · balance -----------------------------------------------------
    section("Balance")
    try:
        wei = client.w3.eth.get_balance(account.address)
        gen = wei / 10**18
        print(f"  {gen:.6f} GEN  ({wei} wei)")
        if wei == 0:
            problems.append(
                "this account has no GEN. Fund it at https://testnet-faucet.genlayer.foundation — "
                "an empty wallet is the usual cause of 'execution reverted'."
            )
    except Exception as error:  # noqa: BLE001
        print(f"  unavailable ({error})")

    # -- 8 · fee policy ---------------------------------------------------
    section("Fees")
    try:
        policy = client.get_current_fee_policy()
        print(f"  policy                 {policy}")
    except Exception as error:  # noqa: BLE001
        print(f"  policy unavailable     ({error})")

    try:
        estimate = client.estimate_transaction_fees()
        value = estimate.get("feeValue", estimate.get("fee_value"))
        print(f"  estimate for a deploy  feeValue={value}")
        if value:
            print(f"                         ≈ {int(value) / 10**18:.6f} GEN")
    except Exception as error:  # noqa: BLE001
        print(f"  estimate FAILED        {error}")
        problems.append(
            f"fee estimation fails: {error}. This is the call that reverts during deployment."
        )

    # -- 9 · is the fee manager the version this SDK expects? --------------
    fee_manager = (chain.fee_manager_contract or {}).get("address")
    section("Fee manager compatibility")
    print(f"  address                 {fee_manager or '(none in this preset)'}")
    if fee_manager:
        try:
            from eth_utils import keccak

            required = ["GENPerTimeUnit()", "storageUnitPrice()", "quoteGasPrice()", "messageFeeParamsBudgetFloor()"]
            missing = []
            for signature in required:
                selector = "0x" + keccak(text=signature)[:4].hex()
                try:
                    raw = client.w3.eth.call({"to": client.w3.to_checksum_address(fee_manager), "data": selector})
                    print(f"  {signature:<32} present (value {int(raw.hex(), 16)})")
                except Exception:  # noqa: BLE001 - a revert means the method is absent
                    print(f"  {signature:<32} MISSING")
                    missing.append(signature)
            if missing:
                problems.append(
                    "the deployed fee manager is missing "
                    + ", ".join(missing)
                    + ". genlayer-py 0.19 needs them, so every fee estimate reverts — this SDK and this "
                    "network are out of step. Try --network studio_devnet, or ask GenLayer which SDK "
                    "version matches this network today."
                )
        except Exception as error:  # noqa: BLE001
            print(f"  probe unavailable       ({error})")

    # -- 10 · is the network actually processing transactions? -------------
    if args.health_blocks > 0:
        section(f"Network health (last {args.health_blocks} blocks)")
        try:
            found, succeeded, failed, timed_out = scan_consensus_health(
                client, args.health_blocks
            )
            print(f"  consensus events in {args.health_blocks} blocks   {found}")
            print(f"  sampled transactions succeeded          {succeeded}")
            print(f"  sampled transactions reverted           {failed}")
            if timed_out:
                print("  (stopped early at the time budget)")
            if not found:
                print("  no consensus activity in this window — the network looks idle.")
            print("  note: reverted transactions emit no events, so this counts")
            print("  successful activity only. It cannot measure a failure rate.")
            if found and failed / max(1, succeeded + failed) > 0.5:
                problems.append(
                    f"{failed} of {succeeded + failed} sampled consensus transactions "
                    "reverted. Treat this as a hint, not proof: reverted transactions emit "
                    "no events, so this sample is biased toward successes."
                )
            elif found:
                print("  the consensus layer is accepting transactions")
        except Exception as error:  # noqa: BLE001 - never fail the whole diagnostic
            print(f"  scan unavailable ({str(error).splitlines()[0][:80]})")

    # -- verdict ----------------------------------------------------------
    section("Verdict")
    if not problems:
        print("  everything checks out. Now run:")
        print(f"      python scripts/deploy_contracts.py --network {args.network} --write-env")
        return 0
    for index, problem in enumerate(problems, 1):
        print(f"  {index}. {problem}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
