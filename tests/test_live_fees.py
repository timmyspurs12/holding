"""Consensus v0.6 fee handling in the live adapter.

The point of these tests: the adapter must work with BOTH the 0.19 SDK (which
takes a `fees` argument) and the 0.18 SDK (which does not), without either
version being installed here. Support is detected from the signature, so a fake
client is enough to prove the behaviour.
"""

from __future__ import annotations

import pytest

from services.lib.genlayer.base import AdapterError
from services.lib.genlayer.config import GenLayerConfig
from services.lib.genlayer.live import LiveChain
from services.lib.genlayer.types import NetworkMode

ADDRESS = "0x3333333333333333333333333333333333333333"

ESTIMATE = {
    "distribution": {"rotations": [0], "appealRounds": 0, "totalMessageFees": 0},
    "feeValue": 123456,
    "messageAllocations": [],
    "observed": {"gas": 10},
    "policy": {},
    "simulation": None,
}


class _LegacyClient:
    """The 0.18 shape: write_contract has no `fees` parameter at all.

    Passing fees= raises TypeError, exactly as the real SDK does — which is what
    makes the adapter's signature check worth having.
    """

    def __init__(self, sink):
        self.sink = sink

    def write_contract(self, address=None, function_name=None, args=None, account=None):
        self.sink.write_calls.append({"function_name": function_name, "args": args, "fees": None})
        return b"\x01\x02"


class _ModernClient(_LegacyClient):
    """The 0.19 shape: write_contract takes `fees`."""

    def write_contract(self, address=None, function_name=None, args=None, account=None, fees=None):
        self.sink.write_calls.append({"function_name": function_name, "args": args, "fees": fees})
        return b"\x01\x02"


class FakeClient:
    """Stands in for GenLayerClient. `with_fees` toggles the 0.19 vs 0.18 shape."""

    def __init__(self, with_fees: bool = True, estimate_error: Exception | None = None):
        self.with_fees = with_fees
        self.estimate_error = estimate_error
        self.write_calls: list[dict] = []
        self.estimates: list[dict] = []
        # Bind the shape at construction so inspect.signature() sees a genuine
        # 0.18-style signature (no `fees`) when with_fees is False.
        shape = _ModernClient(self) if with_fees else _LegacyClient(self)
        self.write_contract = shape.write_contract

    def estimate_transaction_fees_for_write(self, address=None, function_name=None, args=None, account=None, **_):
        self.estimates.append({"function_name": function_name})
        if self.estimate_error:
            raise self.estimate_error
        return dict(ESTIMATE)

    def get_transaction_receipt(self, transaction_hash=None, **_):
        return {"status": 5, "result": {"execution_result": "FINISHED_WITH_RETURN"}}


def make_chain(client: FakeClient, **env) -> LiveChain:
    config = GenLayerConfig(
        mode=NetworkMode.TESTNET,
        network="testnet_bradbury",
        rpc_url="https://rpc-bradbury.genlayer.com",
        chain_id=4221,
        registry_address=ADDRESS,
    )
    chain = LiveChain(config)
    chain._client = client
    chain._account = None
    return chain


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    monkeypatch.delenv("HOLDING_FEE_ESTIMATE", raising=False)


def test_the_two_sdk_shapes_are_actually_different():
    """Guard the guard: if both fakes exposed `fees`, every test below would lie."""
    import inspect

    modern = FakeClient(with_fees=True)
    legacy = FakeClient(with_fees=False)
    assert "fees" in inspect.signature(modern.write_contract).parameters
    assert "fees" not in inspect.signature(legacy.write_contract).parameters


def test_fees_are_estimated_per_call_and_attached():
    client = FakeClient(with_fees=True)
    chain = make_chain(client)
    chain.write(ADDRESS, "register_source", [ADDRESS, True])

    assert len(client.estimates) == 1
    assert client.estimates[0]["function_name"] == "register_source"

    sent = client.write_calls[0]
    assert sent["fees"] is not None
    # only the three keys TransactionFeeOptions defines — no policy/simulation leak
    assert set(sent["fees"]) == {"distribution", "feeValue", "messageAllocations"}
    assert sent["fees"]["feeValue"] == 123456


def test_old_sdk_gets_no_fee_argument():
    """0.18 and earlier: the call must go out unchanged, not raise TypeError."""
    client = FakeClient(with_fees=False)
    chain = make_chain(client)
    chain.write(ADDRESS, "register_source", [ADDRESS, True])

    assert len(client.write_calls) == 1
    assert client.write_calls[0]["fees"] is None
    assert client.estimates == []


def test_fee_estimation_failure_falls_back_to_plain_call():
    client = FakeClient(with_fees=True, estimate_error=RuntimeError("node refused the estimate"))
    chain = make_chain(client)
    result = chain.write(ADDRESS, "register_source", [ADDRESS, True])

    assert client.write_calls[0]["fees"] is None
    assert result.simulated is False


def test_fee_estimation_failure_can_be_strict(monkeypatch):
    monkeypatch.setenv("HOLDING_FEE_ESTIMATE", "strict")
    client = FakeClient(with_fees=True, estimate_error=RuntimeError("node refused the estimate"))
    chain = make_chain(client)
    with pytest.raises(AdapterError, match="fee estimation failed"):
        chain.write(ADDRESS, "register_source", [ADDRESS, True])
    assert client.write_calls == []


def test_fees_can_be_switched_off(monkeypatch):
    monkeypatch.setenv("HOLDING_FEE_ESTIMATE", "off")
    client = FakeClient(with_fees=True)
    chain = make_chain(client)
    chain.write(ADDRESS, "register_source", [ADDRESS, True])

    assert client.write_calls[0]["fees"] is None
    assert client.estimates == []


def test_snake_case_estimates_are_accepted():
    """Some SDK builds return fee_value / message_allocations."""

    class SnakeClient(FakeClient):
        def estimate_transaction_fees_for_write(self, **kwargs):
            return {"distribution": {}, "fee_value": 7, "message_allocations": []}

    client = SnakeClient(with_fees=True)
    chain = make_chain(client)
    chain.write(ADDRESS, "register_source", [ADDRESS, True])

    fees = client.write_calls[0]["fees"]
    assert fees == {"distribution": {}, "feeValue": 7, "messageAllocations": []}
