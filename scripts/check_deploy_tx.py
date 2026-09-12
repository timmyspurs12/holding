#!/usr/bin/env python3
"""Check the state of an already-submitted GenLayer transaction. READ-ONLY.

There are two layers, with two different hashes — do not mix them up:

  L2 (EVM)      the "envelope" transaction: an EIP-1559 transaction calling
                addTransaction on the consensus contract. This is the hash
                eth_sendRawTransaction returns — the one deploy_contracts.py
                prints when its receipt wait times out, and the one in the
                explorer link it shows.
                States: PENDING (in the L2 mempool) / MINED / REVERTED /
                UNKNOWN (visible nowhere) / SUPERSEDED (nonce slot already
                used by another transaction — this one can never mine).

  consensus     the GenLayer lifecycle of the consensus txId that the
                consensus contract registered from the envelope's
                NewTransaction/CreatedTransaction logs. It exists only after
                the envelope is mined:
                  Pending → Proposing → Committing → Revealing → Accepted →
                  Finalized   (or Canceled / ValidatorsTimeout / LeaderTimeout)
                The deployed contract address for a deploy lives in this
                layer (the stored recipient of the consensus record), not in
                the EVM receipt's contractAddress.

This script never sends anything. It only calls read methods:
  eth_getTransactionByHash, eth_getTransactionReceipt, eth_getTransactionCount,
  eth_getBalance, eth_getBlock, eth_gasPrice,
  ConsensusData.addressManager / getTransactionLifecycle,
  AddressManager.getAddressNonZero,
  ConsensusDataBigRounds.getStoredTransactionDataLight

Usage
-----
    pip install "web3>=7"        # no private key, no genlayer-py needed

    # one-shot check of the envelope hash the deploy script printed
    python scripts/check_deploy_tx.py 0xc5a7...29b62

    # keep watching until a terminal state (or --timeout)
    python scripts/check_deploy_tx.py 0xc5a7...29b62 --watch

    # check a consensus txId directly (e.g. copied from the GenLayer explorer)
    python scripts/check_deploy_tx.py --consensus-tx 0x... --watch

Exit codes: 0 FINALIZED · 1 FAILED · 2 UNKNOWN (not propagated / dropped) ·
3 still PENDING/PROCESSING · 4 finalized but no address exposed.
"""

from __future__ import annotations

import argparse
import os
import time

DEFAULT_CHAINS = {
    "bradbury": {
        "rpc": "https://rpc-bradbury.genlayer.com",
        "evm_explorer": "https://zksync-os-testnet-genlayer.explorer.zksync.dev",
        "genlayer_explorer": "https://explorer-bradbury.genlayer.com",
        "consensus_main": "0x0112Bf6e83497965A5fdD6Dad1E447a6E004271D",
        "consensus_data": "0x85D7bf947A512Fc640C75327A780c90847267697",
    },
    "asimov": {
        "rpc": "https://rpc-asimov.genlayer.com",
        "evm_explorer": "",
        "genlayer_explorer": "https://explorer-asimov.genlayer.com",
        "consensus_main": "0x6CAFF6769d70824745AD895663409DC70aB5B28E",
        "consensus_data": "0x0D9d1d74d72Fa5eB94bcf746C8FCcb312a722c9B",
    },
}

# Protocol status ordinals stored by the consensus contracts (genlayer-py
# ProtocolTransactionStatus, v0.6 "train" protocol).
STATUS_NAMES = {
    0: "Uninitialized",
    1: "Pending",
    2: "Proposing",
    3: "Committing",
    4: "Revealing",
    5: "Accepted",
    6: "Undetermined",
    7: "Finalized",
    8: "Canceled",
    9: "AppealRevealing",
    10: "AppealCommitting",
    11: "ValidatorsTimeout",
    12: "LeaderTimeout",
    13: "LeaderRevealing",
}

EXECUTION_RESULT_NAMES = {
    0: "NOT_VOTED",
    1: "FINISHED_WITH_RETURN",
    2: "FINISHED_WITH_ERROR",
    3: "TIMEOUT",
    4: "NONDET_DISAGREE",
    5: "DETERMINISTIC_VIOLATION",
}

PROCESSING_STATES = (1, 2, 3, 4, 9, 10, 13)  # consensus still moving
ACCEPTED = 5
FINALIZED = 7
FAILED_STATES = (6, 8, 11, 12)               # undetermined / canceled / timeouts


def classify_consensus(stored: int, projected: int) -> tuple[str, str]:
    """Map raw protocol ordinals to the user-facing states."""
    label = f"stored={STATUS_NAMES.get(stored, stored)}, projected={STATUS_NAMES.get(projected, projected)}"
    if stored in FAILED_STATES or projected in FAILED_STATES:
        return "FAILED", label
    if stored == FINALIZED:
        return "FINALIZED", label
    if stored == 0 and projected == 0:
        return "NOT-REGISTERED", label
    if stored == ACCEPTED:
        return "PROCESSING", label + " (accepted — appeal window / finalization pending)"
    if stored == 1:
        return "PENDING", label
    return "PROCESSING", label


# Minimal read ABIs (shapes extracted from genlayer-py 0.19.0rc2's shipped
# ABIs). The big-rounds record has dynamic components; the shapes below only
# have to be structurally valid so web3 can decode the head/tail offsets —
# we only read the static fields (sender, recipient, result, status, txId).
ABI_CONSENSUS_DATA = [
    {"inputs": [], "name": "addressManager",
     "outputs": [{"name": "", "type": "address"}],
     "stateMutability": "view", "type": "function"},
    {
        "inputs": [{"name": "_txId", "type": "bytes32"}, {"name": "_timestamp", "type": "uint256"}],
        "name": "getTransactionLifecycle",
        "outputs": [
            {"name": "storedStatus", "type": "uint8"},
            {
                "components": [
                    {"name": "txId", "type": "bytes32"},
                    {"name": "storedStatus", "type": "uint8"},
                    {"name": "projectedStatus", "type": "uint8"},
                    {"name": "action", "type": "uint8"},
                    {"name": "result", "type": "uint8"},
                    {"name": "resultHash", "type": "bytes32"},
                    {"name": "source", "type": "uint8"},
                    {"name": "sourceRound", "type": "uint256"},
                    {"name": "sourceGeneration", "type": "uint256"},
                    {"name": "sourceRoundContextHash", "type": "bytes32"},
                    {"name": "roundPlanHash", "type": "bytes32"},
                    {"name": "resultRound", "type": "uint256"},
                    {"name": "resultGeneration", "type": "uint256"},
                    {"name": "basisDecisionId", "type": "uint256"},
                    {"name": "context", "type": "uint8"},
                    {"name": "attemptId", "type": "bytes32"},
                    {"name": "boundaryAt", "type": "uint256"},
                    {"name": "evaluatedAt", "type": "uint256"},
                    {"name": "snapshotBlock", "type": "uint256"},
                    {"name": "decisionWindow", "type": "uint256"},
                    {"name": "appealDeadline", "type": "uint256"},
                    {"name": "materializesDecision", "type": "bool"},
                    {"name": "actionOutcomeDeterministic", "type": "bool"},
                ],
                "name": "resolution",
                "type": "tuple",
            },
            {
                "components": [{"name": "decisionId", "type": "bytes32"}, {"name": "txId", "type": "bytes32"}],
                "name": "latestDecision",
                "type": "tuple",
            },
            {"name": "decisionActive", "type": "bool"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
]

ABI_ADDRESS_MANAGER = [
    {"inputs": [{"name": "key", "type": "string"}], "name": "getAddressNonZero",
     "outputs": [{"name": "addr", "type": "address"}],
     "stateMutability": "view", "type": "function"},
]

ABI_BIG_ROUNDS_LIGHT = [
    {
        "inputs": [{"name": "_txId", "type": "bytes32"}],
        "name": "getStoredTransactionDataLight",
        "outputs": [
            {
                "components": [
                    {"name": "observedAt", "type": "uint256"},
                    {"name": "sender", "type": "address"},
                    {"name": "recipient", "type": "address"},
                    {"name": "initialRotations", "type": "uint256"},
                    {"name": "txSlot", "type": "uint256"},
                    {"name": "createdTimestamp", "type": "uint256"},
                    {"name": "lastVoteTimestamp", "type": "uint256"},
                    {"name": "randomSeed", "type": "bytes32"},
                    {"name": "result", "type": "uint8"},
                    {"name": "txExecutionHash", "type": "bytes32"},
                    {"name": "txCalldata", "type": "bytes"},
                    {"name": "eqBlocksOutputs", "type": "bytes"},
                    {
                        "components": [{"name": "a", "type": "bytes"}, {"name": "b", "type": "bytes"}],
                        "name": "messages",
                        "type": "tuple[]",
                    },
                    {"name": "queueType", "type": "uint8"},
                    {"name": "queuePosition", "type": "uint256"},
                    {"name": "activator", "type": "address"},
                    {"name": "lastLeader", "type": "address"},
                    {"name": "status", "type": "uint8"},
                    {"name": "txId", "type": "bytes32"},
                    {
                        "components": [
                            {"name": "proposal_block", "type": "uint256"},
                            {"name": "last_block", "type": "uint256"},
                        ],
                        "name": "readStateBlockRange",
                        "type": "tuple",
                    },
                    {"name": "numOfRounds", "type": "uint256"},
                    {"components": [{"name": "round", "type": "uint256"}], "name": "lastRound", "type": "tuple"},
                    {"name": "consumedValidatorsCount", "type": "uint256"},
                ],
                "name": "",
                "type": "tuple",
            }
        ],
        "stateMutability": "view",
        "type": "function",
    }
]


def probe_envelope(w3, envelope: str, sender: str = "") -> dict:
    """Read-only snapshot of the EVM-layer state of the envelope tx.

    `sender` is the known deployer address. When the tx object has vanished
    (dropped from the mempool), the account diagnostics still come from it,
    which is what lets the drop-cause analysis reason about balance/nonce.
    """
    probe = {
        "state": "UNKNOWN",
        "tx": None,
        "receipt": None,
        "nonce_latest": None,
        "nonce_pending": None,
        "balance": None,
        "base_fee": None,
        "gas_price": None,
        "block_number": None,
        "detail": "",
    }
    try:
        probe["tx"] = w3.eth.get_transaction(envelope)
    except Exception as error:  # noqa: BLE001
        probe["detail"] = f"eth_getTransactionByHash failed: {str(error).splitlines()[0][:100]}"
    tx = probe["tx"]
    if tx is None:
        probe["state"] = "UNKNOWN"
    elif tx.get("blockNumber") is None:
        probe["state"] = "PENDING"
    else:
        try:
            probe["receipt"] = w3.eth.get_transaction_receipt(envelope)
        except Exception:  # noqa: BLE001
            probe["receipt"] = None
        receipt = probe["receipt"]
        if receipt is None:
            probe["state"] = "PENDING"
        elif receipt.get("status") == 1:
            probe["state"] = "MINED"
        else:
            probe["state"] = "FAILED"
            probe["detail"] = "EVM tx reverted (L2 receipt status=0)"
    if probe["state"] in ("PENDING", "UNKNOWN"):
        account = (tx or {}).get("from") or sender
        tx_nonce = (tx or {}).get("nonce")
        if account:
            try:
                probe["nonce_latest"] = w3.eth.get_transaction_count(account)
                probe["nonce_pending"] = w3.eth.get_transaction_count(account, "pending")
                probe["balance"] = w3.eth.get_balance(account)
            except Exception:  # noqa: BLE001
                pass
            # Only meaningful while the tx object is visible: its nonce slot
            # being consumed by a DIFFERENT tx means it can never mine.
            if (
                probe["state"] == "PENDING"
                and tx_nonce is not None
                and probe["nonce_latest"] is not None
                and probe["nonce_latest"] > tx_nonce
            ):
                probe["state"] = "SUPERSEDED"
                probe["detail"] = f"nonce slot {tx_nonce} was already used by another transaction"
    try:
        latest = w3.eth.get_block("latest")
        probe["base_fee"] = latest.get("baseFeePerGas")
        probe["block_number"] = latest.get("number")
    except Exception:  # noqa: BLE001
        pass
    try:
        probe["gas_price"] = w3.eth.gas_price
    except Exception:  # noqa: BLE001
        pass
    return probe


def envelope_diagnostics(probe: dict) -> list[str]:
    lines = []
    if probe["block_number"] is not None:
        lines.append(f"chain head block {probe['block_number']}")
    if probe["base_fee"] is not None:
        lines.append(f"block base fee {probe['base_fee'] / 1e9:.3f} gwei")
    if probe["gas_price"] is not None:
        lines.append(f"network gas price {probe['gas_price'] / 1e9:.3f} gwei")
    if probe["nonce_latest"] is not None:
        extra = ""
        if probe["nonce_pending"] is not None and probe["nonce_pending"] > probe["nonce_latest"]:
            extra = f" (+{probe['nonce_pending'] - probe['nonce_latest']} pending in mempool)"
        lines.append(f"account nonce {probe['nonce_latest']}{extra}")
    if probe["balance"] is not None:
        lines.append(f"account balance {probe['balance'] / 1e18:.6f} GEN")
    return lines


def likely_dropped_cause(probe: dict) -> str:
    base_fee = probe["base_fee"] or 0
    gas_price = probe["gas_price"]
    # genlayer-py 0.19 builds the envelope with maxFeePerGas = baseFee + 2 gwei
    sdk_max_fee = base_fee + 2_000_000_000
    if gas_price is not None and gas_price > sdk_max_fee:
        return (
            f"likely cause: the SDK's maxFeePerGas (block base fee + 2 gwei = "
            f"{sdk_max_fee / 1e9:.3f} gwei) is below the current network gas price "
            f"({gas_price / 1e9:.3f} gwei) — the sequencer never included it, so it "
            f"aged out of the mempool"
        )
    if probe["balance"] is not None and gas_price is not None and probe["balance"] < gas_price * 5_000_000:
        return "likely cause: account balance is below gas price × a deploy-size gas limit — the tx was dropped for lack of funds"
    if probe["nonce_pending"] is not None and probe["nonce_latest"] is not None and probe["nonce_pending"] > probe["nonce_latest"]:
        return "likely cause: the tx may still be queued behind other pending transactions of the same account"
    return "likely cause: the tx was not propagated from the RPC node to the block producer (or was dropped) — re-sending is safe only after you have confirmed it is absent from every node you used"


def consensus_tx_id_from_receipt(w3, receipt, consensus_address: str) -> str:
    """Decode NewTransaction/CreatedTransaction logs from the EVM receipt."""
    if not receipt:
        return ""
    new_topic = w3.keccak(text="NewTransaction(bytes32,address,address)").hex()
    created_topic = w3.keccak(text="CreatedTransaction(bytes32,uint256)").hex()
    consensus_address = consensus_address.lower()
    for log in receipt.get("logs") or []:
        topics = log.get("topics") or []
        if len(topics) < 2:
            continue
        if (log.get("address") or "").lower() != consensus_address:
            continue
        if topics[0].hex() in (new_topic, created_topic):
            return "0x" + topics[1].hex()
    return ""


class ConsensusReader:
    """Read-only access to the consensus layer via plain web3 calls."""

    def __init__(self, w3, chain: dict):
        self.w3 = w3
        self.data = w3.eth.contract(
            address=w3.to_checksum_address(chain["consensus_data"]), abi=ABI_CONSENSUS_DATA
        )
        self._big_rounds_address = None

    def _big_rounds(self):
        if self._big_rounds_address is None:
            manager_address = self.data.functions.addressManager().call()
            manager = self.w3.eth.contract(
                address=self.w3.to_checksum_address(manager_address), abi=ABI_ADDRESS_MANAGER
            )
            self._big_rounds_address = manager.functions.getAddressNonZero("ConsensusDataBigRounds").call()
        return self.w3.eth.contract(
            address=self.w3.to_checksum_address(self._big_rounds_address), abi=ABI_BIG_ROUNDS_LIGHT
        )

    def snapshot(self, tx_id: str) -> dict:
        """Read-only consensus state: (state, label, deployed_address, exec_result)."""
        snap = {"state": "NOT-REGISTERED", "label": "no consensus record", "address": "", "exec_result": ""}
        try:
            lifecycle = self.data.functions.getTransactionLifecycle(self.w3.to_bytes(hexstr=tx_id), 0).call()
        except Exception as error:  # noqa: BLE001
            snap["label"] = f"lifecycle read failed: {str(error).splitlines()[0][:80]}"
            return snap
        stored = int(lifecycle[0])
        resolution = lifecycle[1]
        projected = int(resolution.projectedStatus)
        state, label = classify_consensus(stored, projected)
        snap["state"] = state
        snap["label"] = label
        if state == "NOT-REGISTERED":
            return snap
        try:
            record = self._big_rounds().functions.getStoredTransactionDataLight(
                self.w3.to_bytes(hexstr=tx_id)
            ).call()
        except Exception:  # noqa: BLE001
            return snap
        recipient = record.recipient
        if recipient and recipient != "0x0000000000000000000000000000000000000000":
            snap["address"] = recipient
        exec_result = record.result
        snap["exec_result"] = EXECUTION_RESULT_NAMES.get(exec_result, str(exec_result))
        if state == "FINALIZED" and exec_result != 1:
            snap["state"] = "FAILED"
            snap["label"] += f" (execution result {snap['exec_result']})"
        return snap


def mmss(seconds: float) -> str:
    seconds = int(seconds)
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def check_consensus(w3, chain: dict, args, tx_id: str, start: float, quiet_once: bool = False) -> int:
    reader = ConsensusReader(w3, chain)
    deadline = time.monotonic() + (args.timeout if args.watch else 0)
    last_line = None
    while True:
        snap = reader.snapshot(tx_id)
        state = snap["state"]
        line = f"{state:<12} {snap['label']}"
        if snap["exec_result"]:
            line += f" · execution {snap['exec_result']}"
        if line != last_line or args.watch:
            if args.watch or not quiet_once:
                print(f"[{mmss(time.monotonic() - start)}] {line}")
            last_line = line

        if state == "FINALIZED":
            if snap["address"]:
                print(f"    deployed contract address: {snap['address']}")
                print("    resume the remaining deployment steps without redeploying:")
                print(f"        python scripts/deploy_contracts.py --network {args.network} "
                      f"--registry-address {snap['address']} --write-env")
            else:
                print("    finalized, but the stored record did not expose a contract address")
                print("    copy the 'Created contract' address from the explorer and resume with")
                print("        --registry-address 0x<THE ADDRESS THE EXPLORER SHOWS>")
            return 0 if snap["address"] else 4

        if state == "FAILED":
            print("    the consensus decision failed — no contract was created")
            print("    a fresh deployment is the only path forward (same code, new nonce)")
            return 1

        if state == "NOT-REGISTERED":
            if not args.watch:
                print("    the consensus layer does not know this txId yet (envelope not mined, or wrong hash)")
                return 2
            if time.monotonic() >= deadline:
                return 2
            time.sleep(args.interval)
            continue

        # PENDING / PROCESSING
        if not args.watch:
            print("    still in flight — keep watching:  --watch")
            return 3
        if time.monotonic() >= deadline:
            print(f"    still {state} after the {args.timeout:.0f}s watch budget — keep watching")
            print("    GenLayer finality is not a race: an appeal window can keep a transaction")
            print("    ACCEPTED for a while before FINALIZED. Re-run the same command to continue.")
            return 3
        time.sleep(args.interval)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only status checker for an already-submitted GenLayer transaction.",
        epilog="exit codes: 0 FINALIZED · 1 FAILED · 2 UNKNOWN · 3 PENDING/PROCESSING · 4 finalized, no address exposed",
    )
    parser.add_argument("envelope", nargs="?", default="", help="EVM envelope hash (what eth_sendRawTransaction returned)")
    parser.add_argument("--consensus-tx", default="", help="check a consensus txId directly instead of an envelope hash")
    parser.add_argument("--network", default="bradbury", choices=sorted(DEFAULT_CHAINS))
    parser.add_argument("--rpc", default=os.getenv("GENLAYER_RPC_URL", ""), help="override the RPC URL")
    parser.add_argument("--sender", default=os.getenv("GENLAYER_DEPLOYER", ""),
                        help="deployer address (no key needed) — enriches the drop "
                             "diagnostics with balance/nonce when the tx is not visible")
    parser.add_argument("--watch", action="store_true", help="poll until a terminal state or --timeout")
    parser.add_argument("--timeout", type=float, default=600.0, help="watch budget in seconds (default 600)")
    parser.add_argument("--interval", type=float, default=30.0, help="seconds between polls (default 30)")
    args = parser.parse_args(argv)

    from web3 import Web3

    chain = dict(DEFAULT_CHAINS[args.network])
    rpc = args.rpc or chain["rpc"]
    w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 30}))
    if not w3.is_connected():
        print(f"error: cannot reach RPC {rpc}")
        return 2

    start = time.monotonic()
    print(f"chain      {args.network} ({rpc})")
    print(f"head block {w3.eth.block_number}")

    if args.consensus_tx:
        tx_id = args.consensus_tx.strip()
        print(f"consensus  {tx_id}")
        return check_consensus(w3, chain, args, tx_id, start)

    if not args.envelope:
        parser.error("pass an envelope hash or --consensus-tx")

    envelope = args.envelope.strip()
    print(f"envelope   {envelope}")
    if chain["evm_explorer"]:
        print(f"evm        {chain['evm_explorer']}/tx/{envelope}")
    if chain["genlayer_explorer"]:
        print(f"consensus  {chain['genlayer_explorer']}/tx/<consensus txId, once the envelope is mined>")

    deadline = time.monotonic() + (args.timeout if args.watch else 0)
    last_line = None
    while True:
        probe = probe_envelope(w3, envelope, args.sender.strip())
        state = probe["state"]
        if state == "MINED":
            receipt = probe["receipt"] or {}
            line = f"MINED    block {receipt.get('blockNumber') or probe['tx'].get('blockNumber')}"
        elif state == "PENDING":
            line = "PENDING  in the L2 mempool — not in a block yet"
        elif state == "FAILED":
            line = f"FAILED   {probe['detail']}"
        elif state == "SUPERSEDED":
            line = f"FAILED   {probe['detail']}"
        else:
            line = "UNKNOWN  not in any block and not in this node's mempool"

        if line != last_line or args.watch:
            print(f"[{mmss(time.monotonic() - start)}] {state:<8} {line}")
            last_line = line

        if state in ("FAILED", "SUPERSEDED"):
            for extra in envelope_diagnostics(probe):
                print(f"    {extra}")
            return 1

        if state == "UNKNOWN":
            if not args.watch or time.monotonic() >= deadline:
                for extra in envelope_diagnostics(probe):
                    print(f"    {extra}")
                print(f"    {likely_dropped_cause(probe)}")
                print("    nothing to wait for — this transaction is not progressing anywhere visible")
                print("    (this script never sends; a fresh deployment is safe only after you")
                print("    have confirmed the old one is absent from every node you used)")
                return 2
            time.sleep(args.interval)
            continue

        if state == "PENDING":
            if not args.watch or time.monotonic() >= deadline:
                for extra in envelope_diagnostics(probe):
                    print(f"    {extra}")
                print("    keep watching:  --watch")
                return 3
            time.sleep(args.interval)
            continue

        # MINED — resolve the consensus layer
        receipt = probe["receipt"] or {}
        tx_id = consensus_tx_id_from_receipt(w3, receipt, chain["consensus_main"])
        if not tx_id:
            print("    EVM tx succeeded but no NewTransaction/CreatedTransaction log was found")
            print("    — the consensus contract did not register a GenLayer transaction")
            return 1
        print(f"    consensus tx {tx_id}")
        if chain["genlayer_explorer"]:
            print(f"    {chain['genlayer_explorer']}/tx/{tx_id}")
        return check_consensus(w3, chain, args, tx_id, start, quiet_once=True)


if __name__ == "__main__":
    raise SystemExit(main())
