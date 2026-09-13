"""Failure handling in scripts/deploy_contracts.py.

The point of these tests: a dropped connection must never be mistaken for an
answer from the chain. That single confusion produced two operator-visible
harms on Bradbury — the script inferred the consensus ABI from a socket error,
and it reported "nothing was submitted" for a send the node may well have
accepted.

Neither genlayer-py nor web3 is installed here (see test_live_compat.py for the
same constraint), so a fake client stands in. What that proves is the script's
*decision logic*: how it classifies an error, when it is willing to re-send, and
what it tells the operator. It cannot prove anything about the real SDK's
exception types, which is why is_transport_error() also matches on message text.
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
    """Import scripts/deploy_contracts.py by path (it is not a package)."""
    path = ROOT / "scripts" / "deploy_contracts.py"
    spec = importlib.util.spec_from_file_location("deploy_contracts_under_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


deploy = _load_deploy_script()


DEPLOYER = "0xf8e604137A2F4b213AC115D33fee170EB5a63282"

# The exact failure reported from the Bradbury deploy: Windows Winsock 10053,
# wrapped by requests, wrapped again by the SDK.
WINDOWS_ABORT_TEXT = (
    "Request to https://rpc-bradbury.genlayer.com failed: ('Connection aborted.', "
    "ConnectionAbortedError(10053, 'An established connection was aborted by the "
    "software in your host machine', None, 10053, None))"
)


def windows_abort() -> Exception:
    """The real exception type the host stack raises."""
    return ConnectionAbortedError(
        10053, "An established connection was aborted by the software in your host machine"
    )


def wrapped_abort() -> Exception:
    """The same failure as the SDK surfaces it: text only, foreign type."""
    return RuntimeError(WINDOWS_ABORT_TEXT)


class ContractRevert(Exception):
    """Stand-in for web3's ContractLogicError — an answer from the chain."""


def revert() -> Exception:
    return ContractRevert("execution reverted")


class _FakeEth:
    def __init__(self, nonces):
        self._nonces = list(nonces)

    def get_transaction_count(self, address):
        if not self._nonces:
            raise AssertionError("nonce read past the scripted sequence")
        outcome = self._nonces.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class _FakeW3:
    def __init__(self, nonces):
        self.eth = _FakeEth(nonces)


class _FakeAccount:
    address = DEPLOYER


class FakeClient:
    """Just enough of a genlayer-py client for the decision paths under test."""

    def __init__(self, deploy_outcomes=(), nonces=(), fee_policy_outcomes=()):
        self.w3 = _FakeW3(nonces)
        self.account = _FakeAccount()
        self._deploy_outcomes = list(deploy_outcomes)
        self._fee_policy_outcomes = list(fee_policy_outcomes)
        self.deploy_calls = 0
        self.fee_policy_calls = 0

    def deploy_contract(self, code=None, args=None, account=None, **kwargs):
        self.deploy_calls += 1
        outcome = self._deploy_outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    def get_current_fee_policy(self):
        self.fee_policy_calls += 1
        outcome = self._fee_policy_outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


@pytest.fixture(autouse=True)
def _no_sleeping(monkeypatch):
    """Retries must be tested without waiting for them."""
    monkeypatch.setattr(deploy.time, "sleep", lambda _seconds: None)


# ---------------------------------------------------------------------------
# classification: the primitive every fix below depends on
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "error",
    [
        windows_abort(),
        wrapped_abort(),
        ConnectionResetError(10054, "An existing connection was forcibly closed"),
        TimeoutError("timed out"),
        RuntimeError("HTTPSConnectionPool: Max retries exceeded with url"),
        RuntimeError("502 Server Error: Bad Gateway for url: https://rpc-bradbury"),
    ],
    ids=["winsock", "wrapped", "reset", "timeout", "max-retries", "bad-gateway"],
)
def test_transport_failures_are_recognised(error):
    assert deploy.is_transport_error(error) is True


@pytest.mark.parametrize(
    "error",
    [
        revert(),
        ContractRevert("FeesDistributionMissing"),
        RuntimeError("execution reverted: InsufficientFees"),
        ValueError("nonce too low"),
    ],
    ids=["revert", "fees-missing", "insufficient-fees", "nonce-too-low"],
)
def test_chain_verdicts_are_not_called_transport_failures(error):
    """A revert is an answer. Treating it as 'no answer' would hide real faults."""
    assert deploy.is_transport_error(error) is False


def test_read_nonce_distinguishes_unreadable_from_zero():
    """None means 'we could not ask'; 0 means 'the chain said zero'."""
    readable = FakeClient(nonces=[0])
    assert deploy.read_nonce(readable, readable.account) == 0

    broken = FakeClient(nonces=[RuntimeError("connection aborted")])
    assert deploy.read_nonce(broken, broken.account) is None

    assert deploy.read_nonce(None, None) is None


# ---------------------------------------------------------------------------
# fix 1 · the consensus-ABI probe must not guess from a dropped socket
# ---------------------------------------------------------------------------


def test_probe_reports_fee_support_when_the_chain_answers():
    client = FakeClient(fee_policy_outcomes=[{"feeValue": 0}])
    assert deploy.fee_aware_selector_is_live(client, attempts=3, delay=0) is True
    assert client.fee_policy_calls == 1


def test_probe_treats_a_revert_as_no_fee_machinery_without_retrying():
    """The legitimate fallback path: one revert is a definitive answer."""
    client = FakeClient(fee_policy_outcomes=[revert()])
    assert deploy.fee_aware_selector_is_live(client, attempts=5, delay=0) is False
    assert client.fee_policy_calls == 1


def test_probe_retries_a_transport_failure_then_succeeds():
    client = FakeClient(fee_policy_outcomes=[windows_abort(), {"feeValue": 0}])
    assert deploy.fee_aware_selector_is_live(client, attempts=3, delay=0) is True
    assert client.fee_policy_calls == 2


def test_probe_refuses_to_guess_when_the_rpc_is_unreachable():
    """The regression this fix exists for.

    Previously a persistent connection abort returned False, which made main()
    print "this network does not implement the v0.6 fee-bearing addTransaction"
    and force FEE_MODE=off — a wrong protocol decision inferred from a dead
    socket. Unreachable must be a distinct, loud outcome.
    """
    client = FakeClient(fee_policy_outcomes=[windows_abort()] * 4)
    with pytest.raises(deploy.NetworkUnavailable):
        deploy.fee_aware_selector_is_live(client, attempts=4, delay=0)
    assert client.fee_policy_calls == 4


def test_probe_exhaustion_message_offers_the_explicit_escape_hatch():
    client = FakeClient(fee_policy_outcomes=[wrapped_abort()] * 2)
    with pytest.raises(deploy.NetworkUnavailable) as excinfo:
        deploy.fee_aware_selector_is_live(client, attempts=2, delay=0)
    message = str(excinfo.value)
    assert "--consensus-abi" in message
    assert "refusing to guess" in message


# ---------------------------------------------------------------------------
# fix 3 · a deploy is re-sent only when the nonce proves the first was lost
# ---------------------------------------------------------------------------


def test_deploy_retries_when_the_nonce_proves_nothing_landed():
    client = FakeClient(
        deploy_outcomes=[windows_abort(), "0xdeadbeef"],
        # nonce read before the first send, then again after the abort: unchanged
        nonces=[7, 7],
    )
    tx = deploy.deploy_with_retry(client, "code", ["owner"], client.account, {}, "registry", attempts=3, delay=0)
    assert tx == "0xdeadbeef"
    assert client.deploy_calls == 2


def test_deploy_never_resends_once_the_nonce_moves():
    """The abort happened *after* the node accepted the send."""
    client = FakeClient(
        deploy_outcomes=[windows_abort(), "0xshouldneverhappen"],
        nonces=[7, 8],
    )
    with pytest.raises(ConnectionAbortedError):
        deploy.deploy_with_retry(client, "code", ["owner"], client.account, {}, "registry", attempts=3, delay=0)
    assert client.deploy_calls == 1  # a second registry would be the harm


def test_deploy_never_resends_when_the_nonce_cannot_be_read():
    """Unreadable is not 'safe to retry' — it is 'we do not know'."""
    client = FakeClient(
        deploy_outcomes=[windows_abort(), "0xshouldneverhappen"],
        nonces=[7, RuntimeError("connection aborted")],
    )
    with pytest.raises(ConnectionAbortedError):
        deploy.deploy_with_retry(client, "code", ["owner"], client.account, {}, "registry", attempts=3, delay=0)
    assert client.deploy_calls == 1


def test_deploy_never_resends_when_the_first_nonce_was_unreadable():
    client = FakeClient(
        deploy_outcomes=[windows_abort(), "0xshouldneverhappen"],
        nonces=[RuntimeError("connection aborted"), 7],
    )
    with pytest.raises(ConnectionAbortedError):
        deploy.deploy_with_retry(client, "code", ["owner"], client.account, {}, "registry", attempts=3, delay=0)
    assert client.deploy_calls == 1


def test_deploy_does_not_retry_a_chain_verdict():
    """A revert will revert again; retrying only wastes the operator's time."""
    client = FakeClient(deploy_outcomes=[revert()], nonces=[7])
    with pytest.raises(ContractRevert):
        deploy.deploy_with_retry(client, "code", ["owner"], client.account, {}, "registry", attempts=3, delay=0)
    assert client.deploy_calls == 1


def test_deploy_gives_up_after_the_configured_attempts():
    client = FakeClient(
        deploy_outcomes=[windows_abort()] * 3,
        nonces=[7, 7, 7],
    )
    with pytest.raises(ConnectionAbortedError):
        deploy.deploy_with_retry(client, "code", ["owner"], client.account, {}, "registry", attempts=3, delay=0)
    assert client.deploy_calls == 3


# ---------------------------------------------------------------------------
# fix 2 · what the operator is told after a failed deploy
# ---------------------------------------------------------------------------


EXPLORER = "https://explorer-bradbury.genlayer.com"


def test_failure_report_never_claims_nothing_was_submitted_after_an_abort():
    """The regression this fix exists for.

    The old code printed "no transaction hash was returned, so nothing was
    submitted." whenever the error text held no hash — which is exactly what a
    connection abort looks like even when the node accepted the transaction.
    """
    client = FakeClient(nonces=[8])  # nonce moved 7 -> 8
    out = _capture_report(wrapped_abort(), client, nonce_before=7)
    assert "nothing was submitted" not in out
    assert "WAS submitted" in out
    assert f"{EXPLORER}/address/{DEPLOYER}" in out
    assert "--registry-address" in out


def test_failure_report_confirms_nothing_was_submitted_when_nonce_is_unchanged():
    client = FakeClient(nonces=[7])
    out = _capture_report(windows_abort(), client, nonce_before=7)
    assert "nothing was submitted" in out
    assert "re-running is safe" in out


def test_failure_report_says_when_it_cannot_prove_either_way():
    client = FakeClient(nonces=[RuntimeError("connection aborted")])
    out = _capture_report(windows_abort(), client, nonce_before=7)
    assert "cannot be proven" in out
    assert f"{EXPLORER}/address/{DEPLOYER}" in out
    # it must not fall back to the old false reassurance
    assert "so nothing was submitted" not in out


def test_failure_report_says_when_no_nonce_was_captured():
    client = FakeClient(nonces=[7])
    out = _capture_report(windows_abort(), client, nonce_before=None)
    assert "cannot be proven" in out


def test_failure_report_still_surfaces_a_hash_found_in_the_error_text():
    tx = "0x" + "ab" * 32
    client = FakeClient()
    out = _capture_report(RuntimeError(f"TimeExhausted while waiting for {tx}"), client, nonce_before=7)
    assert tx in out
    assert f"{EXPLORER}/tx/{tx}" in out


def test_failure_report_calls_a_revert_a_rejection():
    client = FakeClient()
    out = _capture_report(revert(), client, nonce_before=7)
    assert "the node rejected the call" in out
    assert "transport failure" not in out


def _capture_report(error, client, nonce_before) -> str:
    import io
    from contextlib import redirect_stdout

    buffer = io.StringIO()
    with redirect_stdout(buffer):
        deploy.report_deploy_failure(
            "registry deploy", error, EXPLORER, client, client.account, nonce_before
        )
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# fix 4 · --write-env must be idempotent
# ---------------------------------------------------------------------------


ENV_BODY = """
# HOLDING — deployed testnet_bradbury
GENLAYER_NETWORK=bradbury
HOLDING_REGISTRY_ADDRESS=0xAAAA000000000000000000000000000000000001
ADJUDICATOR_ADDRESS=0xBBBB000000000000000000000000000000000002
"""


@pytest.fixture()
def env_root(tmp_path, monkeypatch):
    """Point the script's ROOT at a scratch dir so tests never touch the real .env."""
    monkeypatch.setattr(deploy, "ROOT", tmp_path)
    return tmp_path


def test_write_env_creates_a_marked_block(env_root):
    deploy.write_env_block(ENV_BODY)
    text = (env_root / ".env").read_text(encoding="utf-8")
    assert deploy.ENV_BLOCK_BEGIN in text
    assert deploy.ENV_BLOCK_END in text
    assert text.count("HOLDING_REGISTRY_ADDRESS=") == 1


def test_write_env_replaces_rather_than_stacking(env_root):
    """A resumed deploy used to append a second set of addresses.

    python-dotenv keeps the last value, so the app silently switched registries
    while the source and attestor registrations stayed on the first one.
    """
    deploy.write_env_block(ENV_BODY)
    second = ENV_BODY.replace(
        "0xAAAA000000000000000000000000000000000001",
        "0xCCCC000000000000000000000000000000000003",
    )
    deploy.write_env_block(second)
    deploy.write_env_block(second)

    text = (env_root / ".env").read_text(encoding="utf-8")
    assert text.count("HOLDING_REGISTRY_ADDRESS=") == 1
    assert text.count("ADJUDICATOR_ADDRESS=") == 1
    assert text.count(deploy.ENV_BLOCK_BEGIN) == 1
    assert "0xCCCC000000000000000000000000000000000003" in text
    assert "0xAAAA000000000000000000000000000000000001" not in text


def test_write_env_preserves_unrelated_settings(env_root):
    """The operator's own keys — including the private key — must survive."""
    (env_root / ".env").write_text(
        "GENLAYER_PRIVATE_KEY=0xsecret\nSOME_OTHER=thing\n", encoding="utf-8"
    )
    deploy.write_env_block(ENV_BODY)
    deploy.write_env_block(ENV_BODY)

    text = (env_root / ".env").read_text(encoding="utf-8")
    assert text.count("GENLAYER_PRIVATE_KEY=0xsecret") == 1
    assert "SOME_OTHER=thing" in text
    assert text.count("HOLDING_REGISTRY_ADDRESS=") == 1
    # the operator's settings stay above the managed block, not swallowed by it
    assert text.index("GENLAYER_PRIVATE_KEY") < text.index(deploy.ENV_BLOCK_BEGIN)


def test_write_env_reports_which_action_it_took(env_root):
    assert "appended" in deploy.write_env_block(ENV_BODY)
    assert "updated" in deploy.write_env_block(ENV_BODY)


def test_write_env_treats_addresses_as_literal_text(env_root):
    """re.sub would interpret a backslash or \\1 in the replacement."""
    awkward = ENV_BODY.replace(
        "0xAAAA000000000000000000000000000000000001",
        "back\\slash\\1group",
    )
    deploy.write_env_block(awkward)
    text = (env_root / ".env").read_text(encoding="utf-8")
    assert "back\\slash\\1group" in text
