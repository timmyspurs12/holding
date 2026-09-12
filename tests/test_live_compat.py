"""Live adapter compatibility across genlayer-py generations.

0.19 renamed things the adapter depends on:

  * `wait_for_transaction_receipt(status=…)` became `wait_until='finalized'`
  * the numeric `status` field became a `lifecycle` block of {state, outcome}
  * `create_client(chain=…)` never accepted a *string*, only a chain object

Each is covered here with a stand-in, because neither SDK can be installed in
CI. What matters is that the adapter picks the right shape from what it is
given, so "does this deploy work on the live network" is answered by these
tests rather than by a funded wallet.
"""

from __future__ import annotations

import sys
import types

import pytest

from services.lib.genlayer.base import LiveUnavailable
from services.lib.genlayer.config import GenLayerConfig
from services.lib.genlayer.live import LiveChain
from services.lib.genlayer.types import NetworkMode

ADDRESS = "0x3333333333333333333333333333333333333333"


def make_chain() -> LiveChain:
    config = GenLayerConfig(
        mode=NetworkMode.TESTNET,
        network="testnet_bradbury",
        rpc_url="https://rpc-bradbury.genlayer.com",
        chain_id=4221,
        registry_address=ADDRESS,
    )
    return LiveChain(config)


# -- waiting for finality ------------------------------------------------


class _ModernWaiter:
    def wait_for_transaction_receipt(self, transaction_hash=None, wait_until="decided", interval=3000, retries=10):
        return {"mode": "modern", "transaction_hash": transaction_hash, "wait_until": wait_until}


class _LegacyWaiter:
    def wait_for_transaction_receipt(self, transaction_hash=None, status="ACCEPTED", interval=3000, retries=10):
        return {"mode": "legacy", "transaction_hash": transaction_hash, "status": status}


def test_modern_sdk_is_waited_with_wait_until():
    chain = make_chain()
    chain._client = _ModernWaiter()
    result = chain._wait_for_finality("0xabc")
    assert result["mode"] == "modern"
    assert result["wait_until"] == "finalized"


def test_legacy_sdk_is_waited_with_status():
    chain = make_chain()
    chain._client = _LegacyWaiter()
    result = chain._wait_for_finality("0xabc")
    assert result["mode"] == "legacy"
    assert result["status"] == "FINALIZED"


# -- receipt parsing ----------------------------------------------------


def test_parse_0_18_shape():
    receipt = LiveChain._parse(
        {
            "status": 7,
            "result": {"execution_result": "FINISHED_WITH_RETURN"},
            "consensus_data": {"finality_timestamp": 1700000000},
        },
        "0xabc",
    )
    assert receipt.status_code == 7
    assert receipt.execution_result == "FINISHED_WITH_RETURN"
    assert receipt.is_final is True
    assert receipt.finality_timestamp == 1700000000


def test_parse_0_19_finalized_accepted():
    receipt = LiveChain._parse(
        {
            "lifecycle": {"state": "finalized", "outcome": "accepted"},
            "tx_execution_result_name": "FINISHED_WITH_RETURN",
            "consensus_data": {},
        },
        "0xabc",
    )
    assert receipt.status_code == 7
    assert receipt.status == "FINALIZED"
    assert receipt.execution_result == "FINISHED_WITH_RETURN"
    assert receipt.is_final is True


def test_parse_0_19_finalized_but_undetermined_is_not_final():
    """Status alone is not success — the adapter must not call this a holding."""
    receipt = LiveChain._parse(
        {"lifecycle": {"state": "finalized", "outcome": "undetermined"}, "result_name": "NONDET_DISAGREE"},
        "0xabc",
    )
    assert receipt.status_code == 6
    assert receipt.is_final is False


def test_parse_0_19_processing_phase():
    receipt = LiveChain._parse({"lifecycle": {"state": "processing", "phase": "revealing"}}, "0xabc")
    assert receipt.status_code == 4
    assert receipt.status == "REVEALING"
    assert receipt.is_final is False


def test_parse_0_19_protocol_status_block():
    receipt = LiveChain._parse(
        {"lifecycle": {"stored_status": 7, "stored_status_name": "FINALIZED"}},
        "0xabc",
    )
    assert receipt.status_code == 7


def test_parse_unknown_shape_is_not_final():
    receipt = LiveChain._parse({"nothing": "recognisable"}, "0xabc")
    assert receipt.status_code is None
    assert receipt.is_final is False


# -- client construction ------------------------------------------------


@pytest.fixture()
def fake_sdk(monkeypatch):
    """Install a stand-in genlayer_py with a chains module and a recorder."""
    module = types.ModuleType("genlayer_py")
    chains = types.SimpleNamespace(testnet_bradbury="BRADBURY", localnet="LOCALNET")
    calls = []

    def create_client(chain=None, endpoint=None, account=None):
        calls.append({"chain": chain, "endpoint": endpoint})
        return f"client({chain},{endpoint})"

    module.chains = chains
    module.create_client = create_client
    monkeypatch.setitem(sys.modules, "genlayer_py", module)
    return calls


def test_chain_is_resolved_to_an_object_not_a_string(fake_sdk):
    """create_client() crashes on a str: 'str' object has no attribute 'rpc_urls'."""
    chain = make_chain()
    assert chain._build_client() == "client(BRADBURY,https://rpc-bradbury.genlayer.com)"
    assert fake_sdk[0]["chain"] == "BRADBURY"


def test_unknown_network_refuses_rather_than_using_the_wrong_chain(fake_sdk):
    config = GenLayerConfig(
        mode=NetworkMode.MAINNET, network="mainnet", rpc_url="https://rpc.example", registry_address=ADDRESS
    )
    with pytest.raises(LiveUnavailable, match="no chain preset named 'mainnet'"):
        LiveChain(config)._build_client()
    assert fake_sdk == []


def test_missing_sdk_is_reported_as_unavailable(monkeypatch):
    monkeypatch.setitem(sys.modules, "genlayer_py", None)
    with pytest.raises(LiveUnavailable, match="genlayer-py is not installed"):
        make_chain()._build_client()
