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
* A dropped connection is not a verdict from the chain, and is never treated as
  one. The consensus-ABI probe distinguishes a revert (this network has no fee
  machinery) from a transport failure (no answer at all) and refuses to guess:
  it retries, then stops and asks for --consensus-abi fees|legacy. Pass that
  flag to skip the probe entirely.
* Deploys are retried only when the account nonce proves the previous attempt
  never landed, so a flaky link cannot produce a duplicate registry. Tunables:
  HOLDING_DEPLOY_RETRIES (default 3), HOLDING_DEPLOY_RETRY_DELAY (default 15s),
  HOLDING_ABI_PROBE_RETRIES (default 5), HOLDING_ABI_PROBE_DELAY (default 5s).
* --write-env replaces a marked block in .env rather than appending, so
  resuming a partial deploy cannot leave two competing sets of addresses.
"""

from __future__ import annotations

# Bump with every fix. Printed at startup so a stale copy is obvious.
BUILD_ID = "2026-09-13.a (transport-vs-revert classification, nonce-guarded deploy retry, idempotent .env)"

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


# --- transport failures are not contract verdicts ---------------------------
# A dropped socket and a contract revert are indistinguishable to a bare
# `except Exception`, but they mean opposite things: a revert is an *answer*
# from the chain, a dropped socket is *no answer at all*. Conflating the two is
# what made this script guess the consensus ABI from a network blip and then
# report "nothing was submitted" for a deploy the node may already have
# accepted. Every classification below goes through is_transport_error().
TRANSPORT_ERROR_MARKERS = (
    "connection aborted",
    "connection reset",
    "connection refused",
    "connection broken",
    "connectionbroken",
    "remotedisconnected",
    "incompleteread",
    "max retries exceeded",
    "failed to establish a new connection",
    "temporarily failed to resolve",
    "name or service not known",
    "nodename nor servname",
    "timed out",
    "timeout",
    "bad gateway",
    "service unavailable",
    "gateway time-out",
    # Windows Winsock codes: the host stack tore the connection down.
    "10053",
    "10054",
    "10060",
    "10061",
)


class NetworkUnavailable(RuntimeError):
    """The RPC could not be reached, so the chain returned no verdict at all."""


def is_transport_error(error) -> bool:
    """True when `error` means "the request never got an answer".

    Exception *type* is trusted only for the builtin network errors; everything
    else is classified by message text, because web3 and requests wrap transport
    failures in their own exception types (a requests ConnectionError is not the
    builtin one) while leaving the underlying Winsock text in the message.
    """
    if isinstance(error, (ConnectionError, TimeoutError)):
        return True
    text = str(error).lower()
    return any(marker in text for marker in TRANSPORT_ERROR_MARKERS)


def read_nonce(client, account):
    """The account's transaction count, or None when it cannot be read.

    None is deliberately distinct from a number. A nonce we failed to read is
    NOT evidence that nothing was sent, and every caller must treat it that way
    rather than defaulting to "safe to retry".
    """
    if client is None or account is None:
        return None
    try:
        return client.w3.eth.get_transaction_count(account.address)
    except Exception:  # noqa: BLE001 - an unreadable nonce is itself informative
        return None


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


def report_deploy_failure(
    label: str,
    error,
    explorer: str,
    client=None,
    account=None,
    nonce_before=None,
) -> None:
    """Report a failed deploy without claiming more than the evidence supports.

    The absence of a tx hash in the error text is NOT proof that nothing was
    submitted: a socket can be aborted after the node already accepted
    eth_sendRawTransaction, and then the reply — hash included — never arrives.
    Telling the operator "nothing was submitted" invites a re-run that leaves a
    second registry behind, so the nonce settles it when it can and the output
    says plainly when it cannot.
    """
    print(f"\n{label} did not return cleanly: {error}")
    tx = extract_tx_hash(error)
    if tx:
        print(f"  transaction submitted: {tx}")
        if explorer:
            print(f"  {explorer}/tx/{tx}")
        print("  it may still be processing — check the explorer above.")
        print("  if it finalised, resume without redeploying:")
        print("      --registry-address 0x<THE ADDRESS THE EXPLORER SHOWS>")
        return

    if not is_transport_error(error):
        # The chain answered, and the answer was no. Nothing was submitted.
        print("  no transaction hash was returned; the node rejected the call.")
        return

    print("  this was a network/transport failure — the chain returned no verdict.")
    nonce_now = read_nonce(client, account)
    if nonce_before is not None and nonce_now is not None:
        if nonce_now != nonce_before:
            print(f"  ! the deployer nonce moved {nonce_before} -> {nonce_now}, so a transaction")
            print("    WAS submitted even though the connection dropped. Do NOT re-run as-is;")
            print("    check whether it landed:")
            if explorer and account is not None:
                print(f"      {explorer}/address/{account.address}")
            print("    if it finalised, resume without redeploying:")
            print("      --registry-address 0x<THE ADDRESS THE EXPLORER SHOWS>")
        else:
            print(f"  the deployer nonce is unchanged at {nonce_now}, so nothing was submitted.")
            print("  re-running is safe once the connection is stable.")
        return

    print("  whether it was submitted cannot be proven from here (the nonce could not be")
    print("  read, or was not captured before the send). CHECK THE EXPLORER FIRST:")
    if explorer and account is not None:
        print(f"      {explorer}/address/{account.address}")
    print("  re-running on top of a deploy that did land leaves two registries behind.")


def deploy_with_retry(
    client,
    code: str,
    deploy_args: list,
    account,
    fees: dict,
    label: str,
    attempts: int = 0,
    delay: float = 0.0,
) -> str:
    """Send a deploy, retrying only when the nonce proves nothing was submitted.

    A deploy is the largest request of the whole run — the entire contract
    source travels in calldata, ~29 kB for HoldingRegistry — so it is the call
    most likely to be cut off by an unstable link or an over-eager firewall, and
    it previously had no retry at all while fee estimation had ten.

    Retrying a *send* is not free: a blind retry duplicates a deploy that
    actually landed. The nonce is therefore the gate. Unchanged means the send
    was genuinely lost and can be repeated; moved OR unreadable means we cannot
    prove it was lost, so the error propagates to report_deploy_failure instead.
    """
    attempts = attempts or max(1, int(os.getenv("HOLDING_DEPLOY_RETRIES", "3")))
    delay = delay or float(os.getenv("HOLDING_DEPLOY_RETRY_DELAY", "15"))
    nonce_before = read_nonce(client, account)
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            return client.deploy_contract(code=code, args=deploy_args, account=account, **fees)
        except Exception as error:  # noqa: BLE001 - classified below
            last_error = error
            if not is_transport_error(error):
                raise
            nonce_now = read_nonce(client, account)
            if nonce_before is None or nonce_now is None or nonce_now != nonce_before:
                # Cannot prove the send was lost, so never re-send it.
                raise
            if attempt < attempts:
                print(
                    f"  … {label} attempt {attempt}/{attempts} lost the connection; nonce still "
                    f"{nonce_now}, nothing was submitted — retrying in {delay:.0f}s"
                )
                time.sleep(delay)
    raise last_error


def write_and_wait(client, registry_address: str, function: str, args: list, label: str, account=None) -> bool:
    """Send an owner-only write, wait for FINALIZED, and confirm it took."""
    print(f"{function:<22}", end="", flush=True)
    fees = fee_kwargs(
        client,
        function,
        address=registry_address,
        function_name=function,
        args=args,
        account=account,
    )
    tx = client.write_contract(
        address=registry_address, function_name=function, args=args, account=account, **fees
    )
    receipt = wait_for_finality(client, tx)
    status_name = status_name_of(receipt)
    print(f"{tx[:18]}…  {status_name or 'finalized'}")
    if status_name and status_name != "FINALIZED":
        print(f"  ! {label} did not finalize (status {status_name}); finish it by hand")
        return False
    return True


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


def fee_aware_selector_is_live(client, attempts: int = 0, delay: float = 0.0) -> bool:
    """True when the network answers the v0.6 fee policy call.

    Only a *revert* proves the fee-bearing addTransaction is missing here. A
    dropped socket proves nothing about the chain, so transport failures are
    retried and then surfaced as NetworkUnavailable rather than silently
    downgrading the deploy to the pre-fee ABI. That downgrade is not harmless:
    on a genuine v0.6 network it also forces fees off, which reproduces the
    exact "reverts with no reason" / FeesDistributionMissing failure this
    fallback exists to avoid — so one lost packet would decide the protocol
    shape for the whole run.
    """
    attempts = attempts or max(1, int(os.getenv("HOLDING_ABI_PROBE_RETRIES", "5")))
    delay = delay or float(os.getenv("HOLDING_ABI_PROBE_DELAY", "5"))
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            client.get_current_fee_policy()
            return True
        except Exception as error:  # noqa: BLE001 - classified below
            last_error = error
            if not is_transport_error(error):
                return False  # a genuine revert: this chain has no fee machinery
            if attempt < attempts:
                print(
                    f"  … fee-policy probe {attempt}/{attempts} could not reach the RPC "
                    f"({str(error).splitlines()[0][:80]}); retrying in {delay:.0f}s"
                )
                time.sleep(delay)
    raise NetworkUnavailable(
        f"could not reach the RPC to determine the consensus ABI (last error: {last_error}). "
        "A dropped connection says nothing about which ABI this network implements, so "
        "refusing to guess. Restore the connection and re-run, or decide explicitly with "
        "--consensus-abi fees (v0.6 fee-bearing) or --consensus-abi legacy (pre-fee)."
    )


def inject_estimate_gas(client, gas_limit: int) -> None:
    """Give eth_estimateGas an explicit gas limit.

    genlayer-py builds the call with no `gas` field, so the node applies its own
    default cap. A GenLayer deploy carries the whole contract source in
    calldata (~29 kB for HoldingRegistry); under the default cap that runs out
    of gas and surfaces as a bare `execution reverted` with no revert data.
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
        return original(*args, **kwargs)

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


# The .env region this script owns. Marked so a re-run replaces it instead of
# stacking a second copy underneath the first.
ENV_BLOCK_BEGIN = "# >>> HOLDING deploy (managed by scripts/deploy_contracts.py) >>>"
ENV_BLOCK_END = "# <<< HOLDING deploy (managed by scripts/deploy_contracts.py) <<<"


def write_env_block(body: str) -> str:
    """Write the deploy addresses into .env, replacing any previous block.

    A bare append is not idempotent, and the failure is silent: a resumed deploy
    leaves two HOLDING_REGISTRY_ADDRESS lines, python-dotenv keeps the last one,
    and the app quietly switches to a different registry than the one the
    sources and attestors were registered on. Replacing a marked region makes
    re-running safe however many times a deploy was resumed.

    Returns a short description of what it did, for the operator.
    """
    path = ROOT / ".env"
    managed = f"{ENV_BLOCK_BEGIN}\n{body.strip()}\n{ENV_BLOCK_END}\n"
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    pattern = re.compile(
        re.escape(ENV_BLOCK_BEGIN) + r".*?" + re.escape(ENV_BLOCK_END) + r"\n?",
        re.DOTALL,
    )
    if pattern.search(existing):
        # A lambda keeps `managed` literal: re.sub would otherwise interpret any
        # backslash or group reference inside the addresses.
        updated = pattern.sub(lambda _match: managed, existing)
        action = "updated the managed block in .env"
    else:
        prefix = existing.rstrip("\n")
        updated = (prefix + "\n\n" if prefix else "") + managed
        action = "appended a managed block to .env"
    path.write_text(updated, encoding="utf-8")
    return action


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
        "--adjudicator-address",
        default=os.getenv("HOLDING_ADJUDICATOR_ADDRESS", ""),
        help="skip the adjudicator deploy and use this one (resume a partial deploy)",
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
        help="seconds to wait for the raw transaction receipt (default 600)",
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
    # An explicit --consensus-abi is an instruction, not a hint: honour it
    # without probing, so a flaky link can never override it and no needless
    # RPC round-trip stands between the operator and the deploy.
    if CONSENSUS_ABI_MODE == "auto":
        try:
            fee_selector_live = fee_aware_selector_is_live(client)
        except NetworkUnavailable as error:
            print(f"\n  ! {error}")
            return 1
    else:
        fee_selector_live = CONSENSUS_ABI_MODE == "fees"
        print(f"  · consensus ABI forced to {'fee-bearing (v0.6)' if fee_selector_live else 'legacy (pre-fee)'} by --consensus-abi")
    use_legacy = CONSENSUS_ABI_MODE == "legacy" or (
        CONSENSUS_ABI_MODE == "auto" and not fee_selector_live
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
    inject_estimate_gas(client, args.estimate_gas)
    raise_receipt_timeout(client, args.tx_timeout)

    if args.diagnose:
        return run_diagnose(client, args, account, chain_name)

    owner = args.owner or account.address
    explorer = EXPLORERS.get(chain_name, "")

    print(f"deploying to {chain_name} from {account.address}")
    print(f"registry owner: {owner}\n")

    registry_address = (args.registry_address or "").strip()
    if registry_address:
        # 1 · resume — the registry already exists, so only the adjudicator is left
        print(f"using registry        {registry_address} (--registry-address, not deploying)")
        if not confirm_source(client, registry_address, account.address):
            pass  # a read that fails here is not fatal; registration below will tell us
        print()
    else:
        # 1 · registry
        registry_fees = fee_kwargs(client, "registry deploy")
        nonce_before = read_nonce(client, account)
        try:
            registry_tx = deploy_with_retry(
                client, registry_code, [owner], account, registry_fees, "registry deploy"
            )
        except Exception as error:  # noqa: BLE001 - the tx hash is inside the message
            report_deploy_failure(
                "registry deploy", error, explorer, client, account, nonce_before
            )
            return 1
        print(f"registry deploy tx    {registry_tx}")
        if explorer:
            print(f"  {explorer}/tx/{registry_tx}")

        registry_receipt = wait_for_finality(client, registry_tx)
        registry_address = contract_address(registry_receipt)
        if not registry_address:
            print("\nThe receipt did not expose a contract address.")
            print("Open the explorer link above and copy the 'Created contract' address,")
            print("then pass it back with --registry-address to deploy the adjudicator.")
            return 1
        print(f"registry address      {registry_address}\n")

    adjudicator_address = (args.adjudicator_address or "").strip()
    if adjudicator_address:
        print(f"using adjudicator    {adjudicator_address} (--adjudicator-address, not deploying)\n")
    elif adjudicator_code:
        # 2 · adjudicator — same fee note as above
        adjudicator_fees = fee_kwargs(client, "adjudicator deploy")
        nonce_before = read_nonce(client, account)
        try:
            adjudicator_tx = deploy_with_retry(
                client,
                adjudicator_code,
                [registry_address, args.domain, args.contract_class, args.panel_size],
                account,
                adjudicator_fees,
                "adjudicator deploy",
            )
        except Exception as error:  # noqa: BLE001 - the tx hash is inside the message
            report_deploy_failure(
                "adjudicator deploy", error, explorer, client, account, nonce_before
            )
            return 1
        print(f"adjudicator deploy tx {adjudicator_tx}")
        if explorer:
            print(f"  {explorer}/tx/{adjudicator_tx}")
        adjudicator_receipt = wait_for_finality(client, adjudicator_tx)
        adjudicator_address = contract_address(adjudicator_receipt)
        print(f"adjudicator address   {adjudicator_address or '(see explorer)'}")

    # 3 · register — the deployer is the owner, so it can add the source and
    #     the attestor. Without this the contracts exist but nothing may emit.
    attestor = (args.attestor or "").strip() or account.address
    if not args.no_register:
        print("\nregistering on the registry contract")
        try:
            if adjudicator_address:
                write_and_wait(client, registry_address, "register_source", [adjudicator_address, True], "register_source", account)
                print(f"  source registered   {confirm_source(client, registry_address, adjudicator_address)}")
            write_and_wait(client, registry_address, "register_attestor", [attestor, True], "register_attestor", account)
            print(f"  attestor            {attestor}")
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
        print(f"\n{write_env_block(env_block)} (git-ignored)")

    print("\nnext:")
    print("  1. restart the Reporter API so it picks up the new addresses")
    print("  2. python scripts/smoke_test.py --expect-mode TESTNET")
    print("  3. open /developers, connect a wallet, propose this contract as a source")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
