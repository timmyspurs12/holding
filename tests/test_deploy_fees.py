"""Consensus v0.6 fee payloads in scripts/deploy_contracts.py.

Three real defects are pinned here, all of them found by reading the shipped
genlayer-py 0.19 source rather than by assuming its API:

1. There is no ``estimate_transaction_fees_for_deploy()`` in the SDK. The
   deploy path must price itself with the generic ``estimate_transaction_fees()``.

2. ``estimate_transaction_fees_for_write()`` is **Studio-only**. On Bradbury it
   raises "Target write fee estimation is only supported on Studio networks".
   That is permanent, so it must fall straight through to the generic
   estimator — not burn ten retries and then give up, and not be mistaken for
   "this chain has no fees" (which would send a feeless, rejectable write).

3. The legacy-ABI fallback used to replace the *whole* consensus ABI with a
   single addTransaction entry. genlayer-py reads the consensus tx id back out
   of the NewTransaction / CreatedTransaction events using that same ABI, so
   the swap made every deploy unable to report its own transaction id.

genlayer-py is not installed here, so fakes stand in; what is asserted is this
script's decision logic.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_deploy_script():
    path = ROOT / "scripts" / "deploy_contracts.py"
    spec = importlib.util.spec_from_file_location("deploy_contracts_fees_under_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


deploy = _load_deploy_script()


STUDIO_ONLY = "Target write fee estimation is only supported on Studio networks"

ESTIMATE = {
    "distribution": {"rotations": [0], "appealRounds": 0},
    "feeValue": 4242,
    "messageAllocations": [],
    # the estimator also returns these; they must not reach the transaction
    "policy": {"enabled": True},
    "observed": {"gas": 10},
}


@pytest.fixture(autouse=True)
def _no_sleeping(monkeypatch):
    monkeypatch.setattr(deploy.time, "sleep", lambda _seconds: None)


@pytest.fixture(autouse=True)
def _default_fee_mode(monkeypatch):
    """fee_kwargs() reads module state and env; keep every test independent."""
    monkeypatch.setattr(deploy, "FEE_MODE", "auto")
    monkeypatch.delenv("HOLDING_FEE_ESTIMATE", raising=False)
    monkeypatch.delenv("HOLDING_FEE_RETRIES", raising=False)


class BradburyLikeClient:
    """A v0.6 chain that is not Studio: per-call estimator refuses, generic works."""

    def __init__(self, generic_error=None, specific_error=None):
        self.generic_error = generic_error
        self.specific_error = specific_error or RuntimeError(STUDIO_ONLY)
        self.specific_calls = 0
        self.generic_calls = 0

    # both accept `fees`, i.e. the 0.19 shape
    def write_contract(self, address=None, function_name=None, args=None, account=None, fees=None):
        return "0x" + "11" * 32

    def deploy_contract(self, code=None, args=None, account=None, fees=None):
        return "0x" + "22" * 32

    def estimate_transaction_fees_for_write(self, **kwargs):
        self.specific_calls += 1
        raise self.specific_error

    def estimate_transaction_fees(self, **kwargs):
        self.generic_calls += 1
        if self.generic_error:
            raise self.generic_error
        return dict(ESTIMATE)


class LegacySDKClient:
    """genlayer-py 0.18: no `fees` parameter anywhere, no estimators."""

    def write_contract(self, address=None, function_name=None, args=None, account=None):
        return "0x" + "33" * 32

    def deploy_contract(self, code=None, args=None, account=None):
        return "0x" + "44" * 32


# ---------------------------------------------------------------------------
# 1 · a deploy is priced, even though the SDK has no deploy-specific estimator
# ---------------------------------------------------------------------------


def test_deploy_is_priced_with_the_generic_estimator():
    """The regression: deploys used to go out with no fees at all.

    fee_kwargs() asked for `estimate_transaction_fees_for_deploy`-style pricing
    via a path that only ran for writes; a v0.6 node rejects the feeless result
    with FeesDistributionMissing.
    """
    client = BradburyLikeClient()
    fees = deploy.fee_kwargs(client, "registry deploy")

    assert "fees" in fees, "a v0.6 deploy must carry a fee payload"
    assert fees["fees"]["feeValue"] == 4242
    assert client.generic_calls == 1
    # a deploy has no calldata-specific estimator, so it must not be attempted
    assert client.specific_calls == 0


def test_deploy_fee_payload_has_only_the_three_transaction_keys():
    """policy/observed are estimator metadata; TransactionFeeOptions rejects them."""
    fees = deploy.fee_kwargs(BradburyLikeClient(), "registry deploy")["fees"]
    assert set(fees) == {"distribution", "feeValue", "messageAllocations"}


# ---------------------------------------------------------------------------
# 2 · a Studio-only estimator falls through instead of failing the deploy
# ---------------------------------------------------------------------------


def test_write_falls_back_to_the_generic_estimator_on_a_non_studio_chain():
    client = BradburyLikeClient()
    fees = deploy.fee_kwargs(
        client,
        "register_source",
        address="0x" + "ab" * 20,
        function_name="register_source",
        args=[],
        account=None,
    )

    assert fees["fees"]["feeValue"] == 4242
    assert client.specific_calls == 1, "the specific estimator is tried first"
    assert client.generic_calls == 1, "and must fall through, not give up"


def test_studio_only_estimator_is_not_retried():
    """It can never succeed on this chain; retrying wastes 10 x 6s of the operator's time."""
    client = BradburyLikeClient()
    deploy.fee_kwargs(
        client,
        "register_source",
        address="0x" + "ab" * 20,
        function_name="register_source",
        args=[],
        account=None,
    )
    assert client.specific_calls == 1


def test_a_chain_without_fees_still_sends_feelessly():
    """The genuine no-fee case must stay a clean, silent degrade."""
    client = BradburyLikeClient(
        generic_error=RuntimeError(
            "Fee policy estimation is not supported on this chain (missing fee_manager_contract)"
        )
    )
    assert deploy.fee_kwargs(client, "registry deploy") == {}


def test_a_real_estimator_outage_is_raised_not_silently_dropped():
    """A transient failure must not degrade to a feeless (rejectable) deploy."""
    client = BradburyLikeClient(generic_error=RuntimeError("connection aborted"))
    with pytest.raises(deploy.FeeEstimationUnavailable):
        deploy.fee_kwargs(client, "registry deploy")


def test_an_018_sdk_sends_no_fee_fields():
    """Passing fees= to 0.18 raises TypeError, so the signature gate must hold."""
    client = LegacySDKClient()
    assert deploy.fee_kwargs(client, "registry deploy") == {}
    assert (
        deploy.fee_kwargs(
            client,
            "register_source",
            address="0x" + "ab" * 20,
            function_name="register_source",
            args=[],
            account=None,
        )
        == {}
    )


def test_fees_can_be_switched_off(monkeypatch):
    monkeypatch.setattr(deploy, "FEE_MODE", "off")
    client = BradburyLikeClient()
    assert deploy.fee_kwargs(client, "registry deploy") == {}
    assert client.generic_calls == 0


def test_zero_mode_still_sends_an_explicit_distribution(monkeypatch):
    """--fees zero must stay on the fee-bearing path (a default distribution is 'no fees')."""
    monkeypatch.setattr(deploy, "FEE_MODE", "zero")
    fees = deploy.fee_kwargs(BradburyLikeClient(), "registry deploy")["fees"]
    assert fees["distribution"]["maxPriceGenPerTimeUnit"] == 1


# ---------------------------------------------------------------------------
# 3 · the legacy ABI swap must keep the events the SDK decodes the tx id from
# ---------------------------------------------------------------------------


class _Chain:
    def __init__(self, abi):
        self.consensus_main_contract = {"address": "0x" + "cd" * 20, "abi": abi}


FEE_BEARING_ABI = [
    {"type": "function", "name": "addTransaction", "inputs": [{"name": "p", "type": "tuple"}]},
    {"type": "event", "name": "NewTransaction", "inputs": []},
    {"type": "event", "name": "CreatedTransaction", "inputs": []},
    {"type": "function", "name": "getTransactionStatus", "inputs": []},
]


def test_legacy_abi_swap_preserves_the_transaction_id_events():
    """The regression: the swap replaced the entire ABI with one function.

    genlayer-py resolves the consensus tx id with
    get_event_by_name("NewTransaction") against this ABI, so dropping the events
    made every fallback deploy raise instead of returning its transaction id.
    """
    patched = deploy.with_legacy_consensus_abi(_Chain(FEE_BEARING_ABI))
    names = [entry.get("name") for entry in patched.consensus_main_contract["abi"]]

    assert "NewTransaction" in names
    assert "CreatedTransaction" in names
    assert "getTransactionStatus" in names


def test_legacy_abi_swap_replaces_only_add_transaction():
    patched = deploy.with_legacy_consensus_abi(_Chain(FEE_BEARING_ABI))
    abi = patched.consensus_main_contract["abi"]

    add = [e for e in abi if e.get("name") == "addTransaction"]
    assert len(add) == 1, "exactly one addTransaction must remain"
    # the pre-fee shape: six flat arguments, not a single tuple
    assert [i["type"] for i in add[0]["inputs"]] == [
        "address",
        "address",
        "uint256",
        "uint256",
        "bytes",
        "uint256",
    ]


def test_legacy_abi_swap_does_not_mutate_the_original_chain():
    chain = _Chain(FEE_BEARING_ABI)
    deploy.with_legacy_consensus_abi(chain)
    original = [e for e in chain.consensus_main_contract["abi"] if e.get("name") == "addTransaction"]
    assert original[0]["inputs"][0]["type"] == "tuple", "the preset must be left alone"


# ---------------------------------------------------------------------------
# 4 · a receipt-wait timeout must not throw away a deploy that was submitted
# ---------------------------------------------------------------------------

EVM_HASH = "0xa9b673f784febbe9bb7670301b2c6932ebbcc3295bb057013d8dec5095db7bb7"
CONSENSUS_ID = "0x" + "7e" * 32

# The exact error from the field report: web3 gives up waiting for the EVM
# receipt and raises from inside genlayer-py, so the consensus tx id is lost
# even though the transaction is on-chain.
TIME_EXHAUSTED = (
    f"Transaction HexBytes('{EVM_HASH}') is not in the chain after 600 seconds"
)


class _Receipt(dict):
    """web3 returns an AttributeDict; status is read as an attribute."""

    status = 1


class _Event:
    def __init__(self, found):
        self._found = found

    def process_receipt(self, receipt, errors=None):
        return self._found


class _Contract:
    def __init__(self, events):
        self._events = events

    def get_event_by_name(self, name):
        if name not in self._events:
            raise ValueError(f"no event {name}")
        return _Event(self._events[name])


class _RecoveryEth:
    def __init__(self, receipt, events):
        self._receipt = receipt
        self._events = events
        self.waits = 0

    def get_transaction_receipt(self, tx_hash):
        if self._receipt is None:
            raise ValueError("not found")
        return self._receipt

    def wait_for_transaction_receipt(self, tx_hash, timeout=None):
        self.waits += 1
        if self._receipt is None:
            raise RuntimeError("not in the chain")
        return self._receipt

    def contract(self, abi=None):
        return _Contract(self._events)


class _RecoveryW3:
    def __init__(self, receipt, events):
        self.eth = _RecoveryEth(receipt, events)

    @staticmethod
    def to_hex(value):
        return value


class RecoveryClient:
    def __init__(self, receipt=None, events=None):
        self.w3 = _RecoveryW3(receipt, events or {})
        self.chain = type("C", (), {"consensus_main_contract": {"abi": FEE_BEARING_ABI}})()


def test_a_mined_deploy_is_recovered_from_the_evm_hash():
    """The reported failure: 600s timeout, no address, 'check the explorer'.

    The EVM transaction was mined; its receipt still carries the consensus tx
    id, so the run can continue instead of stranding the operator.
    """
    client = RecoveryClient(
        receipt=_Receipt(),
        events={"NewTransaction": [{"args": {"txId": CONSENSUS_ID}}]},
    )
    assert deploy.recover_consensus_tx_id(client, EVM_HASH) == CONSENSUS_ID


def test_recovery_also_reads_the_queued_event():
    client = RecoveryClient(
        receipt=_Receipt(),
        events={"CreatedTransaction": [{"args": {"txId": CONSENSUS_ID}}]},
    )
    assert deploy.recover_consensus_tx_id(client, EVM_HASH) == CONSENSUS_ID


def test_recovery_returns_empty_when_the_tx_is_still_pending():
    """Not yet mined is not a failure — it just cannot be recovered yet."""
    assert deploy.recover_consensus_tx_id(RecoveryClient(receipt=None), EVM_HASH) == ""


def test_recovery_is_safe_without_a_hash_or_client():
    assert deploy.recover_consensus_tx_id(None, EVM_HASH) == ""
    assert deploy.recover_consensus_tx_id(RecoveryClient(), "") == ""


def test_deploy_does_not_resend_after_a_receipt_timeout():
    """The harm this prevents: a second registry deployed over a live one."""
    client = RecoveryClient(
        receipt=_Receipt(),
        events={"NewTransaction": [{"args": {"txId": CONSENSUS_ID}}]},
    )
    calls = {"n": 0}

    def deploy_contract(code=None, args=None, account=None, **kwargs):
        calls["n"] += 1
        raise RuntimeError(TIME_EXHAUSTED)

    client.deploy_contract = deploy_contract
    account = type("A", (), {"address": "0x" + "ab" * 20})()

    tx = deploy.deploy_with_retry(
        client, "code", ["owner"], account, {}, "registry deploy", attempts=3, delay=0
    )

    assert tx == CONSENSUS_ID
    assert calls["n"] == 1, "the deploy must never be re-sent once it is on-chain"


def test_failure_report_surfaces_a_recovered_transaction():
    import io
    from contextlib import redirect_stdout

    client = RecoveryClient(
        receipt=_Receipt(),
        events={"NewTransaction": [{"args": {"txId": CONSENSUS_ID}}]},
    )
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        deploy.report_deploy_failure(
            "registry deploy",
            RuntimeError(TIME_EXHAUSTED),
            "https://explorer-bradbury.genlayer.com",
            client,
            type("A", (), {"address": "0x" + "ab" * 20})(),
            7,
        )
    out = buffer.getvalue()
    assert CONSENSUS_ID in out
    assert "do not re-run" in out
