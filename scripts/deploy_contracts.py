#!/usr/bin/env python3
"""Deploy HOLDING to a GenLayer network.

Deploys the two contracts, in order:

  1. HoldingRegistry(owner)                                   -> HLD registry
  2. PrecedentAdjudicator(registry, domain, class, panel)     -> reference consumer

and prints the addresses to paste into .env. Nothing here is simulated: it talks
to the network through genlayer-py and waits for real receipts.

Usage
-----
    pip install -r requirements-live.txt

    export GENLAYER_PRIVATE_KEY=0x...
    python scripts/deploy_contracts.py --network bradbury --write-env

    # check the files and arguments without touching a network
    python scripts/deploy_contracts.py --dry-run

    # resume a deploy that was SUBMITTED but not confirmed (read-only tracking,
    # never resends the transaction):
    python scripts/deploy_contracts.py --network bradbury --registry-tx 0xENVELOPE_HASH
    # or, once you have the deployed address (explorer / check_deploy_tx.py):
    python scripts/deploy_contracts.py --network bradbury --registry-address 0xADDRESS

    # watch any submitted transaction without a key (pure web3, read-only):
    python scripts/check_deploy_tx.py 0xENVELOPE_HASH --watch

Exit codes: 0 success · 1 FAILED (EVM revert / consensus canceled / bad decision)
· 2 UNKNOWN (envelope not propagated / dropped — investigate the printed
diagnostics) · 3 still PENDING/PROCESSING (resume with the printed command)
· 4 finalized but the record did not expose the contract address.

Notes
-----
* Consensus v0.6 requires fee fields on every deploy and write. Those exist in
  genlayer-py >= 0.19.0rc1. This script detects them by signature and estimates
  a fee per call; on 0.18 and earlier it sends the call unchanged, which a v0.6
  node will reject. Set HOLDING_FEE_ESTIMATE=off to suppress fee estimation.
* The deployer account becomes the registry OWNER by default: it is the only
  address that can register source contracts and attestors.
* Deploying is not the last step. The registry refuses holdings from
  unregistered contracts, so this script also calls register_source() for the
  adjudicator and register_attestor() for you. Use --no-register to skip that.
"""

from __future__ import annotations

# Bump with every fix. Printed at startup so a stale copy is obvious.
BUILD_ID = "2026-09-12.a (status-aware finality tracking, resume from submitted tx, read-only tx checker)"

import argparse
import copy
import inspect
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CONTRACTS = ROOT / "contracts"


def load_env() -> None:
    """Read a local .env if one exists.

    Secrets belong in .env (git-ignored), but the SDK reads the process
    environment, so without this a key that looks configured is invisible.
    Never overrides anything already exported — the shell wins.
    """
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    path = ROOT / ".env"
    if path.exists():
        load_dotenv(path, override=False)

DEFAULTS = {
    "bradbury": "testnet_bradbury",
    "asimov": "testnet_asimov",
    "studio_devnet": "studio_devnet",
    "studionet": "studionet",
    "localnet": "localnet",
}

EXPLORERS = {
    "testnet_bradbury": "https://explorer-bradbury.genlayer.com",
    "testnet_asimov": "https://explorer-asimov.genlayer.com",
    "studio_devnet": "https://studio-dev.genlayer.com",
    "studionet": "https://studio.genlayer.com",
    "localnet": "http://127.0.0.1:4000/api",
}

# A GenLayer write has TWO layers with TWO different hashes:
#   L2 (EVM)    the "envelope" tx — an EIP-1559 call to the consensus
#               contract's addTransaction. "In the chain" means its EVM
#               receipt exists (eth_getTransactionReceipt != null). This is
#               the hash eth_sendRawTransaction returns.
#   consensus   the GenLayer lifecycle of the consensus txId registered from
#               the envelope's NewTransaction/CreatedTransaction logs:
#               Pending → Proposing → Committing → Revealing → Accepted →
#               Finalized (or Canceled / timeout). Only exists once the
#               envelope is mined. The GenLayer explorer is keyed by this
#               hash; the EVM-layer explorer is keyed by the envelope hash.
# Bradbury's EVM layer is a ZKsync chain, so envelope txs are inspectable
# there (the GenLayer explorer answers "details unavailable" for an envelope
# hash even when the tx is healthy, because it keys on the consensus txId).
EVM_EXPLORERS = {
    "testnet_bradbury": "https://zksync-os-testnet-genlayer.explorer.zksync.dev",
}


def read_contract(name: str) -> str:
    path = CONTRACTS / f"{name}.py"
    if not path.exists():
        raise SystemExit(f"missing {path} — run `python scripts/render_contract.py` first")
    return path.read_text(encoding="utf-8")


def contract_address(receipt) -> str:
    """Find the deployed contract address in a deploy receipt.

    genlayer-py surfaces the created contract on the receipt/result; the exact
    key has moved between versions, so look in the documented places and fail
    loudly rather than guessing.
    """
    if isinstance(receipt, dict):
        for key in ("contract_address", "address"):
            value = receipt.get(key)
            if value:
                return str(value)
        for container in ("result", "tx_receipt", "consensus_data", "data"):
            nested = receipt.get(container)
            if isinstance(nested, dict):
                for key in ("contract_address", "contractAddress", "created_contract", "address"):
                    value = nested.get(key)
                    if value:
                        return str(value)
    return ""

def sdk_supports_fees(client, method_name: str) -> bool:
    """Consensus v0.6 fee fields exist in genlayer-py >= 0.19.0rc1 only."""
    function = getattr(client, method_name, None)
    if function is None:
        return False
    try:
        return "fees" in inspect.signature(function).parameters
    except (TypeError, ValueError):
        return False


def as_fee_payload(estimate):
    """Reduce an estimate to the three keys TransactionFeeOptions wants."""
    if not isinstance(estimate, dict):
        estimate = dict(getattr(estimate, "items", lambda: [])())
    return {
        "distribution": estimate.get("distribution"),
        "feeValue": estimate.get("feeValue", estimate.get("fee_value", 0)),
        "messageAllocations": estimate.get("messageAllocations", estimate.get("message_allocations", [])),
    }


class FeeEstimationUnavailable(RuntimeError):
    """Fees could not be estimated and a v0.6 node would reject a feeless tx."""


# When a network genuinely has no fee machinery, a feeless transaction is the
# only option and is accepted. These markers mean "this chain has no fees",
# not "try again later".
FEE_UNSUPPORTED_MARKERS = (
    "not supported on this chain",
    "missing fee_manager",
    "no fee manager",
)


# genlayer-py treats the all-zero distribution as "no fees provided" and falls
# back to the legacy transaction shape, which a v0.6 node rejects outright with
# FeesDistributionMissing. Sending an explicit distribution — even a zero-cost
# one — keeps it on the fee-bearing path. maxPriceGenPerTimeUnit is 1 wei purely
# so the payload differs from the default; on Bradbury GENPerTimeUnit() is 0, so
# the real cost is still zero.
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

# "auto" estimates and retries, "zero" sends the explicit zero-cost distribution,
# "off" sends no fee fields at all.
FEE_MODE = (os.environ.get("HOLDING_FEE_MODE") or "auto").strip().lower()


def fee_kwargs(client, label: str, **estimate_kwargs) -> dict:
    """Return {'fees': …} for this call, or {} when fees are genuinely absent.

    A v0.6 node rejects a transaction sent without fees (FeesDistributionMissing),
    so a *transient* estimation failure must not silently degrade to a feeless
    send. It is retried first: a freshly deployed contract is not visible to the
    node's fee simulator for a few seconds, and that race is the common cause.
    """
    if (os.getenv("HOLDING_FEE_ESTIMATE") or "auto").strip().lower() == "off":
        return {}
    if FEE_MODE == "off":
        return {}
    if FEE_MODE == "zero":
        print(f"  · {label}: sending an explicit zero-cost fee distribution (--fees zero)")
        return {
            "fees": {
                "distribution": dict(ZERO_FEE_DISTRIBUTION),
                "feeValue": 0,
                "messageAllocations": [],
            }
        }
    if estimate_kwargs:
        if not sdk_supports_fees(client, "write_contract"):
            return {}
        estimator = getattr(client, "estimate_transaction_fees_for_write", None)
    else:
        if not sdk_supports_fees(client, "deploy_contract"):
            return {}
        estimator = getattr(client, "estimate_transaction_fees", None)
    if estimator is None:
        print(f"  ! {label}: this genlayer-py has no fee estimator; sending without fees")
        return {}
    attempts = max(1, int(os.getenv("HOLDING_FEE_RETRIES", "10")))
    delay = float(os.getenv("HOLDING_FEE_RETRY_DELAY", "6"))
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            return {"fees": as_fee_payload(estimator(**estimate_kwargs))}
        except Exception as error:  # noqa: BLE001 - classification happens below
            last_error = error
            text = str(error).lower()
            if any(marker in text for marker in FEE_UNSUPPORTED_MARKERS):
                print(f"  ! {label}: this network does not support fee estimation; sending without fees")
                return {}
            if attempt < attempts:
                print(
                    f"  … {label}: fee estimate {attempt}/{attempts} failed "
                    f"({str(error).splitlines()[0][:88]}); retrying in {delay:.0f}s"
                )
                time.sleep(delay)
    raise FeeEstimationUnavailable(f"{label}: {last_error}")


# genlayer-py polls 10 times every 3000ms, i.e. it gives up after 30 seconds.
# GenLayer Studio routinely needs longer, so the budget is configurable.
FINALITY_POLL_MS = 3000
FINALITY_TIMEOUT_S = float(os.environ.get("HOLDING_FINALITY_TIMEOUT", "600") or 600)


def wait_for_finality(client, tx: str):
    """Wait for finality on either SDK generation.

    genlayer-py <= 0.18: wait_for_transaction_receipt(status="FINALIZED")
    genlayer-py >= 0.19: wait_for_transaction_receipt(wait_until="finalized")
    """
    function = client.wait_for_transaction_receipt
    try:
        parameters = inspect.signature(function).parameters
    except (TypeError, ValueError):
        parameters = {}
    if "wait_until" in parameters:
        kwargs = {"transaction_hash": tx, "wait_until": "finalized"}
        if "retries" in parameters and FINALITY_TIMEOUT_S > 0:
            kwargs["retries"] = max(1, int(FINALITY_TIMEOUT_S * 1000 / FINALITY_POLL_MS))
            if "interval" in parameters:
                kwargs["interval"] = FINALITY_POLL_MS
        return function(**kwargs)
    return function(transaction_hash=tx, status="FINALIZED")


def status_name_of(receipt) -> str:
    """Best-effort status label, from either receipt shape."""
    name = getattr(receipt, "status_name", None) or (
        receipt.get("status_name") if isinstance(receipt, dict) else None
    )
    if name:
        return str(name).upper()
    if not isinstance(receipt, dict):
        receipt = dict(getattr(receipt, "items", lambda: [])())
    lifecycle = receipt.get("lifecycle")
    if isinstance(lifecycle, dict):
        state = str(lifecycle.get("state") or "")
        outcome = str(lifecycle.get("outcome") or "")
        if state == "finalized":
            return "FINALIZED" if outcome in ("", "accepted") else outcome.upper()
        return (state or outcome).upper()
    return ""


TX_HASH_RE = re.compile(r"0x[0-9a-fA-F]{64}")


def extract_tx_hash(error) -> str:
    """Pull a transaction hash out of an SDK/web3 error message.

    When the node is slow, genlayer-py raises TimeExhausted from deep inside
    web3 and the hash we need to resume is only in the message text.
    """
    match = TX_HASH_RE.search(str(error))
    return match.group(0) if match else ""


# ── status-aware post-submission tracking ─────────────────────────────
#
# The SDK's deploy_contract/write_contract internally wait for the EVM
# receipt of the addTransaction envelope with a blind timeout (web3
# "is not in the chain after N seconds") and only then return the consensus
# txId. When that wait expires, the transaction may still be alive, so we
# keep tracking it read-only. Every wait below distinguishes:
#
#   PENDING      envelope in the L2 mempool, or consensus pending
#   PROCESSING   envelope mined and the consensus lifecycle moving
#                (incl. ACCEPTED waiting out the appeal window)
#   FINALIZED    consensus FINALIZED with an accepted execution
#   FAILED       EVM revert, consensus canceled, or a non-accepted decision
#   UNKNOWN      envelope visible nowhere (dropped / not propagated)
#   SUPERSEDED   the envelope's nonce slot was used by another transaction
#
# None of these paths ever resends a transaction.

STATUS_PENDING = "PENDING"
STATUS_PROCESSING = "PROCESSING"
STATUS_FINALIZED = "FINALIZED"
STATUS_FAILED = "FAILED"
STATUS_UNKNOWN = "UNKNOWN"
STATUS_SUPERSEDED = "SUPERSEDED"

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_UNKNOWN = 2
EXIT_PROCESSING = 3
EXIT_NO_ADDRESS = 4

ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"


def mmss(seconds: float) -> str:
    seconds = int(seconds)
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def probe_envelope(client, envelope: str, sender: str = "") -> dict:
    """Read-only snapshot of the EVM-layer state of an envelope tx.

    `sender` is the known deployer address. When the tx object has vanished
    (dropped from the mempool), the account diagnostics still come from it,
    which is what lets the drop-cause analysis reason about balance/nonce.
    """
    w3 = client.w3
    probe = {
        "state": STATUS_UNKNOWN,
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
        probe["state"] = STATUS_UNKNOWN
    elif tx.get("blockNumber") is None:
        probe["state"] = STATUS_PENDING
    else:
        try:
            probe["receipt"] = w3.eth.get_transaction_receipt(envelope)
        except Exception:  # noqa: BLE001
            probe["receipt"] = None
        receipt = probe["receipt"]
        if receipt is None:
            probe["state"] = STATUS_PENDING
        elif receipt.get("status") == 1:
            probe["state"] = "MINED"
        else:
            probe["state"] = STATUS_FAILED
            probe["detail"] = "EVM tx reverted (L2 receipt status=0)"
    if probe["state"] in (STATUS_PENDING, STATUS_UNKNOWN):
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
                probe["state"] == STATUS_PENDING
                and tx_nonce is not None
                and probe["nonce_latest"] is not None
                and probe["nonce_latest"] > tx_nonce
            ):
                probe["state"] = STATUS_SUPERSEDED
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


def _print_envelope_state(label: str, elapsed: float, probe: dict) -> None:
    state = probe["state"]
    clock = mmss(elapsed)
    if state == "MINED":
        receipt = probe["receipt"] or {}
        block = receipt.get("blockNumber") or (probe["tx"] or {}).get("blockNumber")
        print(f"  … {label:<17} {clock}  MINED    (block {block})")
    elif state == STATUS_PENDING:
        print(f"  … {label:<17} {clock}  PENDING  (in the L2 mempool — not in a block yet)")
    elif state == STATUS_FAILED:
        print(f"  … {label:<17} {clock}  FAILED   ({probe['detail']})")
    elif state == STATUS_SUPERSEDED:
        print(f"  … {label:<17} {clock}  FAILED   ({probe['detail']})")
    else:
        print(f"  … {label:<17} {clock}  UNKNOWN  (no block, not in this node's mempool)")
    if state == STATUS_UNKNOWN:
        for line in envelope_diagnostics(probe):
            print(f"      {line}")


def wait_for_envelope(client, envelope: str, label: str, timeout_s: float,
                      interval_s: float = 5.0, print_every_s: float = 30.0,
                      sender: str = "") -> dict:
    """Status-aware L2-inclusion wait. Read-only: never resends the tx."""
    start = time.monotonic()
    deadline = start + timeout_s
    last_state, last_print = None, -1e9
    while True:
        probe = probe_envelope(client, envelope, sender)
        state = probe["state"]
        elapsed = time.monotonic() - start
        if state != last_state or elapsed - last_print >= print_every_s:
            _print_envelope_state(label, elapsed, probe)
            last_state, last_print = state, elapsed
        if state in ("MINED", STATUS_FAILED, STATUS_SUPERSEDED):
            return probe
        if time.monotonic() >= deadline:
            return probe  # PENDING or UNKNOWN at budget end — caller reports
        time.sleep(interval_s)


def consensus_tx_id_from_receipt(w3, receipt, consensus_address: str) -> str:
    """Decode the consensus txId from the envelope receipt's logs.

    The consensus contract emits NewTransaction(bytes32 txId, address
    recipient, address activator) when a tx is immediately activated, or
    CreatedTransaction(bytes32 txId, uint256 txSlot) when it is queued.
    """
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


def probe_consensus(client, tx_id: str) -> dict:
    """Read-only snapshot of the consensus lifecycle for a registered txId."""
    probe = {"state": STATUS_UNKNOWN, "phase": "", "outcome": "", "tx": None, "detail": ""}
    try:
        tx = client.get_transaction(tx_id=tx_id)
    except Exception as error:  # noqa: BLE001
        probe["detail"] = f"consensus record not readable: {str(error).splitlines()[0][:100]}"
        return probe
    if not isinstance(tx, dict):
        probe["detail"] = "unexpected consensus record shape"
        return probe
    probe["tx"] = tx
    lifecycle = tx.get("lifecycle")
    if not isinstance(lifecycle, dict):
        probe["detail"] = "consensus record has no lifecycle (not registered?)"
        return probe
    state = str(lifecycle.get("state") or "")
    phase = str(lifecycle.get("phase") or "")
    outcome = str(lifecycle.get("outcome") or "")
    probe["phase"], probe["outcome"] = phase, outcome
    if state == "finalized":
        if outcome in ("", "accepted"):
            probe["state"] = STATUS_FINALIZED
        else:
            probe["state"] = STATUS_FAILED
            probe["detail"] = f"finalized with outcome {outcome}"
    elif state == "canceled":
        probe["state"] = STATUS_FAILED
        probe["detail"] = "canceled before finalization"
    elif state == "decided":
        if outcome == "accepted":
            probe["state"] = STATUS_PROCESSING
            probe["phase"] = "accepted — appeal window / finalization pending"
        else:
            probe["state"] = STATUS_FAILED
            probe["detail"] = f"decided with outcome {outcome}"
    elif state == "processing":
        probe["state"] = STATUS_PENDING if phase in ("", "pending", "uninitialized") else STATUS_PROCESSING
    else:
        probe["detail"] = f"unrecognized lifecycle state {state!r}"
    # An accepted-but-erroring execution still has to be reported as failed.
    if probe["state"] == STATUS_FINALIZED:
        name = tx.get("tx_execution_result_name") or tx.get("tx_execution_result")
        if name not in (None, "", "FINISHED_WITH_RETURN", 1):
            probe["state"] = STATUS_FAILED
            probe["detail"] = f"finalized with execution result {name}"
    return probe


def _print_consensus_state(label: str, elapsed: float, probe: dict) -> None:
    state = probe["state"]
    clock = mmss(elapsed)
    if state == STATUS_FINALIZED:
        print(f"  … {label:<17} {clock}  FINALIZED (accepted)")
    elif state == STATUS_FAILED:
        print(f"  … {label:<17} {clock}  FAILED    ({probe['detail']})")
    elif state == STATUS_PENDING:
        print(f"  … {label:<17} {clock}  PENDING   (consensus {probe['phase'] or 'pending'})")
    elif state == STATUS_PROCESSING:
        print(f"  … {label:<17} {clock}  PROCESSING ({probe['phase'] or 'in progress'})")
    else:
        print(f"  … {label:<17} {clock}  UNKNOWN   ({probe['detail']})")


def wait_for_consensus(client, tx_id: str, label: str, timeout_s: float,
                       interval_s: float = 10.0, print_every_s: float = 30.0) -> dict:
    """Status-aware consensus-finality wait. Read-only: never resends the tx."""
    start = time.monotonic()
    deadline = start + timeout_s
    last_state, last_print = None, -1e9
    while True:
        probe = probe_consensus(client, tx_id)
        state = probe["state"]
        elapsed = time.monotonic() - start
        if state != last_state or elapsed - last_print >= print_every_s:
            _print_consensus_state(label, elapsed, probe)
            last_state, last_print = state, elapsed
        if state in (STATUS_FINALIZED, STATUS_FAILED):
            return probe
        if time.monotonic() >= deadline:
            return probe  # still PENDING/PROCESSING — caller reports + resume cmd
        time.sleep(interval_s)


def contract_address_of(tx_simplified) -> str:
    """Extract the deployed contract address from a finalized deploy tx.

    On GenLayer the EVM envelope receipt has NO contractAddress (the envelope
    calls the consensus contract, it is not a CREATE). The created address
    lives in the consensus record — the stored recipient of a deploy — which
    genlayer-py surfaces as data.contract_address / recipient.
    """
    address = contract_address(tx_simplified)
    if address and address.lower() != ZERO_ADDRESS:
        return address
    if isinstance(tx_simplified, dict):
        for key in ("recipient", "to_address"):
            value = tx_simplified.get(key)
            if value and str(value).lower() != ZERO_ADDRESS:
                return str(value)
    return ""


def print_resume_hint(args, envelope: str = "", tx_id: str = "", address: str = "") -> None:
    """Print the exact commands that resume without redeploying anything."""
    print("  resume without redeploying (read-only until it re-submits nothing):")
    if address:
        print(f"      python scripts/deploy_contracts.py --network {args.network} "
              f"--registry-address {address} --write-env")
    elif tx_id:
        print(f"      python scripts/deploy_contracts.py --network {args.network} "
              f"--registry-tx {tx_id} --write-env")
    elif envelope:
        print(f"      python scripts/deploy_contracts.py --network {args.network} "
              f"--registry-tx {envelope} --write-env")
    print(f"  or track it live:  python scripts/check_deploy_tx.py "
          f"{envelope or tx_id or address} --watch")


def finish_consensus(client, tx_id: str, label: str, explorer: str, args,
                     need_address: bool = True) -> tuple[int, dict]:
    """Wait for consensus finality (status-aware) and report the outcome.

    Returns (exit_code, probe). exit codes: 0 FINALIZED · 1 FAILED ·
    3 still PENDING/PROCESSING · 4 finalized but no address exposed.
    """
    probe = wait_for_consensus(client, tx_id, label, args.finality_timeout)
    state = probe["state"]
    if state == STATUS_FINALIZED:
        if need_address:
            address = contract_address_of(probe.get("tx"))
            if not address:
                print(f"\n  ! {label}: FINALIZED, but the record did not expose a contract address.")
                if explorer:
                    print(f"    copy the 'Created contract' address from {explorer}/tx/{tx_id} and resume:")
                    print(f"      python scripts/deploy_contracts.py --network {args.network} "
                          f"--registry-address 0x<THE ADDRESS THE EXPLORER SHOWS> --write-env")
                return EXIT_NO_ADDRESS, probe
            probe["address"] = address
        return EXIT_OK, probe
    if state in (STATUS_PENDING, STATUS_PROCESSING):
        detail = probe.get("phase") or probe.get("detail") or "in progress"
        print(f"\n  ! {label}: still {state} after the {args.finality_timeout:.0f}s wait budget — last state: {detail}")
        print("    GenLayer finality is not a race: an ACCEPTED transaction waits out the")
        print("    appeal window before FINALIZED, so this is expected to keep moving.")
        print("    Nothing was resent. Keep monitoring:")
        if explorer:
            print(f"    {explorer}/tx/{tx_id}")
        print_resume_hint(args, tx_id=tx_id)
        return EXIT_PROCESSING, probe
    print(f"\n  ✗ {label}: FAILED — {probe.get('detail') or state}")
    if explorer:
        print(f"    {explorer}/tx/{tx_id}")
    return EXIT_FAILED, probe


def follow_envelope_to_finality(client, envelope: str, label: str,
                                evm_explorer: str, explorer: str, args,
                                need_address: bool = True,
                                sender: str = "") -> tuple[int, dict]:
    """Track an ALREADY-SUBMITTED envelope tx to a conclusion. Read-only:
    L2 inclusion → consensus txId → consensus finality → deployed address.

    `sender` is the known deployer, used only to enrich the drop diagnostics
    (balance/nonce) when the envelope is no longer visible.
    """
    probe = wait_for_envelope(client, envelope, label, args.tx_timeout, sender=sender)
    state = probe["state"]
    if state == "MINED":
        receipt = probe.get("receipt") or {}
        consensus_address = (client.chain.consensus_main_contract or {}).get("address", "")
        tx_id = consensus_tx_id_from_receipt(client.w3, receipt, consensus_address)
        if not tx_id:
            print(f"\n  ✗ {label}: the EVM tx was mined, but no NewTransaction/CreatedTransaction")
            print("    event was found in its receipt — the consensus layer never registered")
            print("    a GenLayer transaction, so no contract was created.")
            if evm_explorer:
                print(f"    {evm_explorer}/tx/{envelope}")
            return EXIT_FAILED, probe
        print(f"  consensus tx      {tx_id}")
        if explorer:
            print(f"  {explorer}/tx/{tx_id}")
        return finish_consensus(client, tx_id, label + " cons.", explorer, args, need_address)
    if state == STATUS_FAILED:
        print(f"\n  ✗ {label}: FAILED at the EVM layer — {probe.get('detail')}")
        print("    the addTransaction call was rejected by the chain; no consensus")
        print("    transaction was registered and no contract was created.")
        for line in envelope_diagnostics(probe):
            print(f"    {line}")
        return EXIT_FAILED, probe
    if state == STATUS_SUPERSEDED:
        print(f"\n  ✗ {label}: FAILED — {probe.get('detail')}")
        print("    this transaction can never be mined; nothing was deployed.")
        for line in envelope_diagnostics(probe):
            print(f"    {line}")
        return EXIT_FAILED, probe
    if state == STATUS_PENDING:
        print(f"\n  ! {label}: still PENDING after the {args.tx_timeout:.0f}s wait budget —")
        print("    it is in the L2 mempool, so it is alive and nothing must be resent.")
        for line in envelope_diagnostics(probe):
            print(f"    {line}")
        if evm_explorer:
            print(f"    {evm_explorer}/tx/{envelope}")
        print_resume_hint(args, envelope=envelope)
        return EXIT_PROCESSING, probe
    # UNKNOWN
    print(f"\n  ! {label}: UNKNOWN after the {args.tx_timeout:.0f}s wait budget — the envelope is")
    print("    not in any block and not in this node's mempool. It was most likely dropped,")
    print("    so nothing was deployed. Check the diagnostics, then decide whether to re-send")
    print("    a fresh deployment (safe only once the old one is confirmed gone everywhere):")
    for line in envelope_diagnostics(probe):
        print(f"    {line}")
    print(f"    {likely_dropped_cause(probe)}")
    if evm_explorer:
        print(f"    {evm_explorer}/tx/{envelope}")
    return EXIT_UNKNOWN, probe


def raise_receipt_timeout(client, seconds: int) -> None:
    """Give the underlying web3 receipt wait more than its 120 s default.

    GenLayer consensus takes minutes, and the SDK calls
    w3.eth.wait_for_transaction_receipt() without a timeout of its own. A
    partial binding keeps the SDK's own signature intact.
    """
    import functools

    eth = client.w3.eth
    if seconds <= 0 or getattr(eth, "_holding_timeout_patched", False):
        return
    eth.wait_for_transaction_receipt = functools.partial(
        eth.wait_for_transaction_receipt, timeout=seconds
    )
    setattr(eth, "_holding_timeout_patched", True)


def report_deploy_failure(label: str, error, explorer: str, evm_explorer: str = "") -> None:
    print(f"\n{label} did not return cleanly: {error}")
    tx = extract_tx_hash(error)
    if tx:
        print(f"  transaction submitted: {tx} (EVM envelope hash)")
        if evm_explorer:
            print(f"  {evm_explorer}/tx/{tx}   <- the EVM layer (this hash)")
        if explorer and explorer != evm_explorer:
            print(f"  {explorer}/tx/<consensus txId>   <- the consensus layer (different hash)")
        print("  it may still be processing — check the explorer above.")
        print("  track it read-only (nothing is resent):")
        print(f"      python scripts/check_deploy_tx.py {tx} --watch")
        print("  if it finalised, resume without redeploying:")
        print(f"      --registry-tx {tx}")
        print("      --registry-address 0x<THE ADDRESS THE EXPLORER SHOWS>")
    else:
        print("  no transaction hash was returned, so nothing was submitted.")


def write_and_wait(client, registry_address: str, function: str, args: list, label: str, account=None,
                   sent: dict | None = None, explorer: str = "", evm_explorer: str = "", args_cli=None) -> int:
    """Send an owner-only write and track it to FINALIZED (status-aware).

    Returns an exit code: 0 FINALIZED · 1 FAILED · 2 UNKNOWN · 3 still
    PENDING/PROCESSING. A submitted transaction is tracked read-only — this
    function never resends it.
    """
    print(f"{function:<22}", end="", flush=True)
    fees = fee_kwargs(
        client,
        function,
        address=registry_address,
        function_name=function,
        args=args,
        account=account,
    )
    try:
        tx = client.write_contract(
            address=registry_address, function_name=function, args=args, account=account, **fees
        )
    except Exception as error:  # noqa: BLE001 - the tx hash is inside the message
        envelope = extract_tx_hash(error) or (sent or {}).get("envelope")
        if not envelope:
            print(f"  (failed: {str(error).splitlines()[0][:100]})")
            return EXIT_FAILED
        print(f"  (SDK receipt wait timed out — tracking {envelope[:18]}… read-only)")
        code = follow_envelope_to_finality(
            client, envelope, label, evm_explorer, explorer, args_cli,
            need_address=False, sender=getattr(account, "address", ""),
        )[0]
        if sent is not None:
            sent["envelope"] = ""
        print(f"{label:<22}  (tracked the submitted tx; state above)")
        return code
    if sent is not None:
        sent["envelope"] = ""  # consumed: this envelope is now being tracked below
    code, probe = finish_consensus(client, tx, label, explorer, args_cli, need_address=False)
    print(f"{tx[:18]}…  {probe.get('state') or 'finalized'}")
    return code


def confirm_source(client, registry_address: str, address: str) -> bool:
    """Read is_registered_source back — the contract is the source of truth."""
    try:
        return bool(client.read_contract(address=registry_address, function_name="is_registered_source", args=[address]))
    except Exception as error:  # noqa: BLE001 - a read failure must not look like success
        print(f"  ! could not confirm on-chain: {error}")
        return False


# genlayer-py 0.19 encodes every consensus call with the v0.6 fee-bearing
# selector (addTransaction(tuple), 0x35a251fb). Bradbury's deployed contract does
# not implement it, so the call reverts with no reason. The same SDK still ships
# the pre-fee ABI, and forcing it makes the SDK emit addTransaction(address,
# address, uint256, uint256, bytes, uint256) = 0xe71d5196, which the live network
# accepts. Detection is derived from the ABI, so swapping it is all it takes.
LEGACY_ADD_TRANSACTION_ABI = [
    {
        "type": "function",
        "name": "addTransaction",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "sender", "type": "address"},
            {"name": "recipient", "type": "address"},
            {"name": "numOfInitialValidators", "type": "uint256"},
            {"name": "maxRotations", "type": "uint256"},
            {"name": "txData", "type": "bytes"},
            {"name": "validUntil", "type": "uint256"},
        ],
        "outputs": [{"name": "", "type": "bytes32"}],
    }
]

CONSENSUS_ABI_MODE = (os.environ.get("HOLDING_CONSENSUS_ABI") or "auto").strip().lower()


def with_legacy_consensus_abi(chain):
    """Return a copy of `chain` whose consensus ABI is the pre-fee shape."""
    patched = copy.deepcopy(chain)
    contract = dict(patched.consensus_main_contract or {})
    contract["abi"] = LEGACY_ADD_TRANSACTION_ABI
    patched.consensus_main_contract = contract
    return patched


def fee_aware_selector_is_live(client) -> bool:
    """True when the network still answers the v0.6 fee policy call."""
    try:
        client.get_current_fee_policy()
        return True
    except Exception:  # noqa: BLE001 - a revert here is the signal we want
        return False


def inject_estimate_gas(client, gas_limit: int, sent: dict | None = None) -> None:
    """Give eth_estimateGas an explicit gas limit.

    genlayer-py builds the call with no `gas` field, so the node applies its own
    default cap. A GenLayer deploy carries the whole contract source in
    calldata (~29 kB for HoldingRegistry); under the default cap that runs out
    of gas and surfaces as a bare `execution reverted` with no revert data.

    When `sent` is a dict, the hash of every eth_sendRawTransaction result is
    also captured in it (key "envelope", last one wins) — that is the EVM
    envelope hash, which lets the post-submission tracker resume from the
    exact transaction the SDK sent even when the SDK's own receipt wait times
    out and its error message is unhelpful.
    """
    provider = client.provider
    original = provider.make_request

    def patched(*args, **kwargs):
        method = args[0] if args else kwargs.get("method")
        params = args[1] if len(args) > 1 else kwargs.get("params")
        if method == "eth_estimateGas" and params and isinstance(params[0], dict):
            tx = dict(params[0])
            if not tx.get("gas"):
                tx["gas"] = hex(gas_limit)
            rest = list(params[1:])
            if len(args) > 1:
                args = (args[0], [tx] + rest) + tuple(args[2:])
            else:
                kwargs["params"] = [tx] + rest
        result = original(*args, **kwargs)
        if sent is not None and method == "eth_sendRawTransaction" and isinstance(result, dict):
            hash_value = result.get("result")
            if isinstance(hash_value, (str, bytes)):
                sent["envelope"] = (
                    "0x" + bytes(hash_value).hex() if isinstance(hash_value, bytes) else str(hash_value)
                )
        return result

    provider.make_request = patched


KNOWN_REVERTS = {
    "0x8d53e553": "InsufficientFees",
    "0xb4132db3": "MaxPriceExceeded",
    "0x57df8523": "ExecutionBudgetExceeded",
    "0x305e533c": "BudgetTooLow",
    "0xa70732ee": "RollupBudgetBelowFloor",
    "0x632be5a1": "FeeValueMustBeNonZero",
}


def run_diagnose(client, args, account, chain_name) -> int:
    """Print the exact deploy transaction and simulate it. Sends nothing."""
    registry_code = read_contract("HoldingRegistry")
    owner = args.owner or account.address
    w3 = client.w3
    sender = w3.to_checksum_address(account.address)

    print("\n--- diagnose: no transaction will be sent ---")
    print(f"  RPC                  {args.endpoint or list(getattr(client.chain, 'rpc_urls', {}).get('default', {}).get('http', ['']))[0]}")
    print(f"  chain id             {w3.eth.chain_id}")
    print(f"  deployer             {sender}")
    print(f"  balance              {w3.eth.get_balance(sender) / 10 ** 18:.6f} GEN")
    print(f"  nonce                {w3.eth.get_transaction_count(sender)}")
    print(f"  consensus            {client.chain.consensus_main_contract['address']}")
    print(f"  contract             HoldingRegistry.py ({len(registry_code)} bytes)")
    print(f"  constructor args     [{owner}]")
    print(f"  fee model            {FEE_MODE}")
    print(f"  consensus abi        {'legacy (pre-fee)' if CONSENSUS_ABI_MODE != 'fees' and client.chain.consensus_main_contract['abi'] and client.chain.consensus_main_contract['abi'][0]['inputs'][0]['type'] == 'address' else 'fee-bearing (v0.6)'}")

    captured: dict = {}
    provider = client.provider
    original = provider.make_request

    def intercept(*a, **kw):
        method = a[0] if a else kw.get("method")
        params = a[1] if len(a) > 1 else kw.get("params")
        if method == "eth_estimateGas":
            captured["tx"] = dict(params[0])
            raise RuntimeError("__diagnose_stop__")
        return original(*a, **kw)

    provider.make_request = intercept
    build_error = None
    try:
        client.deploy_contract(
            code=registry_code, args=[owner], account=account,
            leader_only=False, consensus_max_rotations=args.panel_size or 3,
        )
    except Exception as error:  # noqa: BLE001
        build_error = str(error)
    finally:
        provider.make_request = original

    tx = captured.get("tx")
    if not tx:
        print(f"\n  transaction was never built: {build_error}")
        return 1

    data = tx.get("data") or "0x"
    print(f"\n  --- transaction genlayer-py would send ---")
    for key in ("to", "from", "value", "nonce", "chainId", "gas",
                "gasPrice", "maxFeePerGas", "maxPriorityFeePerGas"):
        print(f"  {key:<20} {tx.get(key)}")
    print(f"  {'selector':<20} {data[:10]}")
    print(f"  {'calldata':<20} {len(data) // 2 - 1} bytes")

    sim = dict(tx)
    sim["gas"] = hex(args.estimate_gas)
    print(f"\n  --- eth_call simulation (gas={args.estimate_gas}) ---")
    try:
        result = original("eth_call", params=[sim, "latest"])
        print(f"  simulation            ACCEPTED")
        print(f"  return                {str(result.get('result'))[:80]}")
        print("\n  FINAL DIAGNOSIS: the deploy transaction is valid and the")
        print("  network accepts it. Proceed with the real deployment.")
        return 0
    except Exception as error:  # noqa: BLE001
        blob = " ".join(str(x) for x in (
            getattr(error, "data", ""), getattr(error, "message", ""),
            getattr(error, "args", ()), str(error)))
        print("  simulation            REVERTED")
        print(f"  error                 {blob[:300]}")
        named = [n for sel, n in KNOWN_REVERTS.items() if sel in blob]
        if named:
            print(f"  decoded revert        {', '.join(named)}")
        else:
            print("  decoded revert        none matched (empty revert data)")
        print("\n  FINAL DIAGNOSIS: the network rejects this transaction before")
        print("  consensus. Nothing was sent.")
        return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deploy HOLDING contracts to GenLayer")
    parser.add_argument("--network", default="bradbury", choices=sorted(DEFAULTS))
    parser.add_argument("--chain", default="", help="override the genlayer-py chain preset name")
    parser.add_argument("--endpoint", default=os.getenv("GENLAYER_RPC_URL", ""), help="override the RPC URL")
    parser.add_argument("--private-key", default=os.getenv("GENLAYER_PRIVATE_KEY", ""))
    parser.add_argument("--owner", default="", help="registry owner (default: the deployer address)")
    parser.add_argument("--domain", default="digital-commerce")
    parser.add_argument("--contract-class", default="RefundArbiter")
    parser.add_argument("--panel-size", type=int, default=5)
    parser.add_argument("--no-adjudicator", action="store_true", help="deploy the registry only")
    parser.add_argument(
        "--registry-address",
        default=os.getenv("HOLDING_REGISTRY_ADDRESS", ""),
        help="skip the registry deploy and use this one (resume a partial deploy)",
    )
    parser.add_argument(
        "--registry-tx",
        default=os.getenv("HOLDING_REGISTRY_TX", ""),
        help="EVM envelope hash of an already-submitted registry deploy: track it "
             "to finality (read-only, never resends) and continue from the address "
             "it deployed, instead of deploying a new registry",
    )
    parser.add_argument(
        "--adjudicator-address",
        default=os.getenv("HOLDING_ADJUDICATOR_ADDRESS", ""),
        help="skip the adjudicator deploy and use this one (resume a partial deploy)",
    )
    parser.add_argument(
        "--adjudicator-tx",
        default=os.getenv("HOLDING_ADJUDICATOR_TX", ""),
        help="EVM envelope hash of an already-submitted adjudicator deploy: track it "
             "to finality (read-only, never resends) instead of deploying a new one",
    )
    parser.add_argument(
        "--attestor",
        default="",
        help="address allowed to attest finality (default: the deployer address)",
    )
    parser.add_argument(
        "--no-register",
        action="store_true",
        help="deploy only; do not register the adjudicator as a source or add an attestor",
    )
    parser.add_argument("--write-env", action="store_true", help="append addresses to .env")
    parser.add_argument("--dry-run", action="store_true", help="validate locally, deploy nothing")
    parser.add_argument("--diagnose", action="store_true", help="print the exact deploy transaction and simulate it; sends nothing")
    parser.add_argument(
        "--fees",
        choices=["auto", "zero", "off"],
        default=(os.getenv("HOLDING_FEE_MODE") or "auto").strip().lower(),
        help="auto: estimate fees and retry (default). zero: send an explicit "
             "zero-cost distribution, for nodes whose fee manager rejects the "
             "estimator. off: send no fee fields.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"deploy_contracts.py build {BUILD_ID}",
    )
    parser.add_argument(
        "--consensus-abi",
        choices=["auto", "fees", "legacy"],
        default=(os.getenv("HOLDING_CONSENSUS_ABI") or "auto").strip().lower(),
        help="auto: use the pre-fee ABI when the network's fee policy call "
             "reverts (default). fees: always use the v0.6 fee-bearing ABI. "
             "legacy: always use the pre-fee ABI.",
    )
    parser.add_argument(
        "--estimate-gas",
        type=int,
        default=int(os.getenv("HOLDING_ESTIMATE_GAS", "30000000")),
        help="gas limit supplied to eth_estimateGas (default 30000000; the SDK "
             "sends none and the node's default cap is too low for a deploy)",
    )
    parser.add_argument(
        "--finality-timeout",
        type=float,
        default=float(os.getenv("HOLDING_FINALITY_TIMEOUT", "600")),
        help="seconds to wait for GenLayer consensus finality (default 600; "
             "genlayer-py's own default is only 30)",
    )
    parser.add_argument(
        "--tx-timeout",
        type=int,
        default=int(os.getenv("HOLDING_TX_TIMEOUT", "600")),
        help="seconds to wait for the EVM envelope receipt (L2 inclusion, default "
             "600). On timeout the submitted transaction is still tracked "
             "read-only with status-aware polling (PENDING/PROCESSING/FAILED/"
             "UNKNOWN); nothing is resent",
    )
    args = parser.parse_args(argv)
    load_env()
    if not args.private_key:
        args.private_key = os.getenv("GENLAYER_PRIVATE_KEY", "")

    registry_code = read_contract("HoldingRegistry")
    adjudicator_code = read_contract("Adjudicator") if not args.no_adjudicator else ""

    if args.dry_run:
        import ast

        ast.parse(registry_code)
        if adjudicator_code:
            ast.parse(adjudicator_code)
        print("dry run: both contracts parse")
        print(f"  build          {BUILD_ID}")
        print(f"  chain          {args.chain or DEFAULTS[args.network]}")
        print(f"  registry args  owner=<deployer or --owner>")
        print(f"  adjudicator    registry, {args.domain}, {args.contract_class}, {args.panel_size}")
        print("  no network calls were made")
        return 0

    try:
        from genlayer_py import chains, create_account, create_client
    except ImportError:
        raise SystemExit(
            "genlayer-py is not installed. Run: pip install -r requirements-live.txt"
        ) from None

    if not args.private_key:
        raise SystemExit("GENLAYER_PRIVATE_KEY is not set (or pass --private-key)")

    print(f"build {BUILD_ID}\n")
    account = create_account(args.private_key)
    chain_name = args.chain or DEFAULTS[args.network]
    chain = getattr(chains, chain_name)

    client_kwargs = {"chain": chain, "account": account}
    if args.endpoint:
        client_kwargs["endpoint"] = args.endpoint
    client = create_client(**client_kwargs)

    # genlayer-py 0.19 always encodes the v0.6 fee-bearing addTransaction. When
    # the network's fee policy call reverts, that selector is not implemented
    # there and every call reverts with no reason, so fall back to the pre-fee
    # ABI, which the live contract does accept.
    global FINALITY_TIMEOUT_S, FEE_MODE, CONSENSUS_ABI_MODE
    CONSENSUS_ABI_MODE = args.consensus_abi
    use_legacy = CONSENSUS_ABI_MODE == "legacy" or (
        CONSENSUS_ABI_MODE == "auto" and not fee_aware_selector_is_live(client)
    )
    if use_legacy:
        print(
            "  ! this network does not implement the v0.6 fee-bearing addTransaction\n"
            "    (its fee policy call reverts), so genlayer-py's default encoding would\n"
            "    revert with no reason. Switching to the pre-fee consensus ABI."
        )
        client_kwargs["chain"] = with_legacy_consensus_abi(chain)
        client = create_client(**client_kwargs)
        # fees can only travel on the fee-bearing path, so they must be omitted
        FEE_MODE = "off"

    FINALITY_TIMEOUT_S = args.finality_timeout
    if FEE_MODE == "auto":
        FEE_MODE = args.fees
    sent: dict = {}
    inject_estimate_gas(client, args.estimate_gas, sent)
    raise_receipt_timeout(client, args.tx_timeout)

    if args.diagnose:
        return run_diagnose(client, args, account, chain_name)

    owner = args.owner or account.address
    explorer = EXPLORERS.get(chain_name, "")
    evm_explorer = EVM_EXPLORERS.get(chain_name, "")

    print(f"deploying to {chain_name} from {account.address}")
    print(f"registry owner: {owner}\n")

    registry_address = (args.registry_address or "").strip()
    registry_tx_resume = (args.registry_tx or "").strip()
    if registry_address:
        # 1 · resume — the registry already exists, so only the adjudicator is left
        print(f"using registry        {registry_address} (--registry-address, not deploying)")
        if not confirm_source(client, registry_address, account.address):
            pass  # a read that fails here is not fatal; registration below will tell us
        print()
    elif registry_tx_resume:
        # 1 · resume — the registry deploy was already SUBMITTED; track the
        # existing transaction to finality. Read-only: nothing is resent.
        print(f"resuming registry deploy from submitted envelope {registry_tx_resume}")
        print("  (tracking an already-submitted transaction — nothing is resent)")
        if evm_explorer:
            print(f"  {evm_explorer}/tx/{registry_tx_resume}")
        code, probe = follow_envelope_to_finality(
            client, registry_tx_resume, "registry deploy", evm_explorer, explorer, args,
            sender=account.address,
        )
        if code != EXIT_OK:
            return code
        registry_address = probe.get("address", "")
        print(f"\nregistry address      {registry_address}\n")
    else:
        # 1 · registry
        registry_fees = fee_kwargs(client, "registry deploy")
        try:
            registry_tx = client.deploy_contract(
                code=registry_code, args=[owner], account=account, **registry_fees
            )
        except Exception as error:  # noqa: BLE001 - the tx hash is inside the message
            # The SDK's internal receipt wait (a blind eth_getTransactionReceipt
            # poll) gave up, but eth_sendRawTransaction already succeeded — the
            # transaction is submitted and may still be alive. Keep tracking it
            # read-only with status-aware polling before declaring anything.
            envelope = extract_tx_hash(error) or sent.get("envelope")
            if not envelope:
                report_deploy_failure("registry deploy", error, explorer, evm_explorer)
                return EXIT_FAILED
            print(f"\n  ! {str(error).splitlines()[0]}")
            print(f"  the transaction WAS submitted — tracking it read-only (nothing is resent): {envelope}")
            if evm_explorer:
                print(f"  {evm_explorer}/tx/{envelope}")
            code, probe = follow_envelope_to_finality(
                client, envelope, "registry deploy", evm_explorer, explorer, args,
                sender=account.address,
            )
            sent["envelope"] = ""
            if code != EXIT_OK:
                return code
            registry_address = probe.get("address", "")
            print(f"\nregistry address      {registry_address}\n")
        else:
            sent["envelope"] = ""  # consumed: this envelope is now being tracked below
            print(f"registry deploy tx    {registry_tx}")
            if explorer:
                print(f"  {explorer}/tx/{registry_tx}")
            # The SDK already waited for the EVM envelope receipt. What remains
            # is the GenLayer consensus lifecycle — now with status-aware
            # polling that prints PENDING / PROCESSING / FINALIZED / FAILED.
            code, probe = finish_consensus(
                client, registry_tx, "registry cons.", explorer, args
            )
            if code != EXIT_OK:
                return code
            registry_address = probe.get("address", "")
            print(f"registry address      {registry_address}\n")

    adjudicator_address = (args.adjudicator_address or "").strip()
    adjudicator_tx_resume = (args.adjudicator_tx or "").strip()
    if adjudicator_address:
        print(f"using adjudicator    {adjudicator_address} (--adjudicator-address, not deploying)\n")
    elif adjudicator_tx_resume:
        # 2 · resume — the adjudicator deploy was already SUBMITTED; track it.
        print(f"resuming adjudicator deploy from submitted envelope {adjudicator_tx_resume}")
        print("  (tracking an already-submitted transaction — nothing is resent)")
        if evm_explorer:
            print(f"  {evm_explorer}/tx/{adjudicator_tx_resume}")
        code, probe = follow_envelope_to_finality(
            client, adjudicator_tx_resume, "adjudicator deploy", evm_explorer, explorer, args,
            sender=account.address,
        )
        if code != EXIT_OK:
            return code
        adjudicator_address = probe.get("address", "")
        print(f"\nadjudicator address   {adjudicator_address or '(see explorer)'}")
    elif adjudicator_code:
        # 2 · adjudicator — same fee note as above
        adjudicator_fees = fee_kwargs(client, "adjudicator deploy")
        try:
            adjudicator_tx = client.deploy_contract(
                code=adjudicator_code,
                args=[registry_address, args.domain, args.contract_class, args.panel_size],
                account=account,
                **adjudicator_fees,
            )
        except Exception as error:  # noqa: BLE001 - the tx hash is inside the message
            envelope = extract_tx_hash(error) or sent.get("envelope")
            if not envelope:
                report_deploy_failure("adjudicator deploy", error, explorer, evm_explorer)
                return EXIT_FAILED
            print(f"\n  ! {str(error).splitlines()[0]}")
            print(f"  the transaction WAS submitted — tracking it read-only (nothing is resent): {envelope}")
            if evm_explorer:
                print(f"  {evm_explorer}/tx/{envelope}")
            code, probe = follow_envelope_to_finality(
                client, envelope, "adjudicator deploy", evm_explorer, explorer, args,
                sender=account.address,
            )
            sent["envelope"] = ""
            if code != EXIT_OK:
                return code
            adjudicator_address = probe.get("address", "")
            print(f"\nadjudicator address   {adjudicator_address or '(see explorer)'}")
        else:
            sent["envelope"] = ""  # consumed: this envelope is now being tracked below
            print(f"adjudicator deploy tx {adjudicator_tx}")
            if explorer:
                print(f"  {explorer}/tx/{adjudicator_tx}")
            code, probe = finish_consensus(
                client, adjudicator_tx, "adjudicator cons.", explorer, args
            )
            if code != EXIT_OK:
                return code
            adjudicator_address = probe.get("address", "")
            print(f"adjudicator address   {adjudicator_address or '(see explorer)'}")

    # 3 · register — the deployer is the owner, so it can add the source and
    #     the attestor. Without this the contracts exist but nothing may emit.
    attestor = (args.attestor or "").strip() or account.address
    worst_code = EXIT_OK
    if not args.no_register:
        print("\nregistering on the registry contract")
        try:
            if adjudicator_address:
                code = write_and_wait(
                    client, registry_address, "register_source", [adjudicator_address, True],
                    "register_source", account,
                    sent=sent, explorer=explorer, evm_explorer=evm_explorer, args_cli=args,
                )
                worst_code = max(worst_code, code)
                if code == EXIT_OK:
                    print(f"  source registered   {confirm_source(client, registry_address, adjudicator_address)}")
                elif code in (EXIT_PROCESSING, EXIT_UNKNOWN):
                    print("  (register_source not confirmed yet — resume with the command printed above)")
            code = write_and_wait(
                client, registry_address, "register_attestor", [attestor, True],
                "register_attestor", account,
                sent=sent, explorer=explorer, evm_explorer=evm_explorer, args_cli=args,
            )
            worst_code = max(worst_code, code)
            if code == EXIT_OK:
                print(f"  attestor            {attestor}")
            elif code in (EXIT_PROCESSING, EXIT_UNKNOWN):
                print("  (register_attestor not confirmed yet — resume with the command printed above)")
        except FeeEstimationUnavailable as error:
            print(f"\n  ! registration skipped: {error}")
            print("    The contracts are deployed; this step only needs the fee estimator to")
            print("    catch up with them. Re-run the same command with the addresses below")
            print("    and it will resume without redeploying:")
            print(f"      --registry-address {registry_address} --adjudicator-address {adjudicator_address}")
            print("    (or re-run in a minute — nothing was submitted, so there is no duplicate.)")
            return 1
    if args.no_register:
        print("\nskipped registration (--no-register):")
        print("  register_source(<adjudicator>, True) and register_attestor(<you>, True)")
        print("  are still required before any holding can be created.")
    if worst_code != EXIT_OK:
        # Something was submitted but is not confirmed yet (or failed). Stop
        # with the precise state instead of pretending success; the commands
        # above resume it without redeploying anything.
        return worst_code

    env_block = f"""
# HOLDING — deployed {chain_name}
GENLAYER_NETWORK={args.network}
GENLAYER_RPC_URL={args.endpoint or ''}
HOLDING_REGISTRY_ADDRESS={registry_address}
ADJUDICATOR_ADDRESS={adjudicator_address}
HOLDING_DEMO_SEED=false
# Public origin of the Reporter site — stamped into the wallet sign-in message.
# HOLDING_PUBLIC_ORIGIN=https://your-site.example
# Wallets allowed to act as operators (Reporter-side allowlist).
# HOLDING_OPERATOR_ADDRESSES={account.address}
"""
    print("\n--- add to .env ---")
    print(env_block.strip())

    if args.write_env:
        with open(ROOT / ".env", "a", encoding="utf-8") as handle:
            handle.write(env_block)
        print("\nappended to .env (git-ignored)")

    print("\nnext:")
    print("  1. restart the Reporter API so it picks up the new addresses")
    print("  2. python scripts/smoke_test.py --expect-mode TESTNET")
    print("  3. open /developers, connect a wallet, propose this contract as a source")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
