"""Integration tests for the status-aware post-submission tracking in
deploy_contracts.py, using a scripted mock of the web3 read calls and the
SDK client. Run with the venv that has web3 installed:

    python tests/test_deploy_tracking.py
"""
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import deploy_contracts as dc  # noqa: E402
from web3 import Web3  # noqa: E402

CONSENSUS = "0x0112Bf6e83497965A5fdD6Dad1E447a6E004271D"
TXID = "0x" + "cd" * 32
NEW_TOPIC = Web3().keccak(text="NewTransaction(bytes32,address,address)")


class FakeChain:
    consensus_main_contract = {"address": CONSENSUS}


class FakeClient:
    def __init__(self, store):
        self.s = store
        self.w3 = Web3()
        self.chain = FakeChain()
        self.w3.eth = W3EthShim(store)


def make_receipt(status=1, txid=TXID, consensus=CONSENSUS):
    return {
        "status": status,
        "blockNumber": 21521500,
        "logs": [{
            "address": consensus,
            "topics": [NEW_TOPIC, Web3.to_bytes(hexstr=txid), b"\x00" * 20, b"\x00" * 20],
        }],
    }


def base_store():
    return {
        "tx_seq": [
            {"from": "0x" + "11" * 20, "nonce": 7, "blockNumber": None},
            {"from": "0x" + "11" * 20, "nonce": 7, "blockNumber": 21521500},
        ],
        "receipt_seq": [None, make_receipt()],
        "nonce_seq": [7, 7],
        "pending_seq": [8, 8],
        "consensus_seq": [],
        "calls": {"tx": 0, "rcpt": 0, "nonce": 0},
    }


class W3EthShim:
    def __init__(self, store):
        self.s = store

    def get_transaction(self, h):
        seq = self.s["tx_seq"]
        i = min(self.s["calls"]["tx"], len(seq) - 1)
        self.s["calls"]["tx"] += 1
        return seq[i]

    def get_transaction_receipt(self, h):
        seq = self.s["receipt_seq"]
        i = min(self.s["calls"]["rcpt"], len(seq) - 1)
        self.s["calls"]["rcpt"] += 1
        if seq[i] is None:
            from web3.exceptions import TransactionNotFound
            raise TransactionNotFound(h)
        return seq[i]

    def get_transaction_count(self, a, tag=None):
        i = self.s["calls"]["nonce"]
        self.s["calls"]["nonce"] += 1
        seq = self.s["pending_seq"] if tag == "pending" else self.s["nonce_seq"]
        return seq[min(i, len(seq) - 1)]

    def get_balance(self, a):
        return 10 ** 19

    def get_block(self, tag):
        return {"baseFeePerGas": 0, "number": 21521505}

    @property
    def gas_price(self):
        return self.s.get("gas_price", 10 ** 9)


def scripted_consensus(store):
    state = {"n": 0}

    def get_transaction(tx_id=None):
        seq = store["consensus_seq"]
        i = min(state["n"], len(seq) - 1)
        state["n"] += 1
        return seq[i]

    return get_transaction


def args_for(tx_timeout=600, finality_timeout=600):
    return types.SimpleNamespace(network="bradbury", tx_timeout=tx_timeout, finality_timeout=finality_timeout)


def follow(store, envelope, args=None):
    client = FakeClient(store)
    client.get_transaction = scripted_consensus(store)
    return dc.follow_envelope_to_finality(
        client, envelope, "registry deploy", "https://zksync-evm.ex", "https://gl.ex", args or args_for()
    )


def test_pending_to_mined_to_finalized():
    store = base_store()
    store["consensus_seq"] = [
        {"lifecycle": {"state": "processing", "phase": "pending"}},
        {"lifecycle": {"state": "processing", "phase": "revealing"}},
        {"lifecycle": {"state": "finalized", "outcome": "accepted"},
         "data": {"contract_address": "0x" + "aa" * 20},
         "tx_execution_result_name": "FINISHED_WITH_RETURN"},
    ]
    code, probe = follow(store, "0x" + "11" * 32)
    assert code == dc.EXIT_OK, (code, probe)
    assert probe["address"] == "0x" + "aa" * 20, probe
    print("PASS pending→mined→finalized, address extracted")


def test_unknown_dropped():
    store = base_store()
    store["tx_seq"] = [None]
    code, probe = follow(store, "0x" + "22" * 32, args_for(tx_timeout=0.5))
    assert code == dc.EXIT_UNKNOWN, (code, probe)
    assert probe["state"] == dc.STATUS_UNKNOWN
    print("PASS unknown/dropped → EXIT_UNKNOWN")


def test_canceled():
    store = base_store()
    store["tx_seq"] = [store["tx_seq"][1]]
    store["receipt_seq"] = [make_receipt()]
    store["consensus_seq"] = [{"lifecycle": {"state": "canceled"}}]
    code, probe = follow(store, "0x" + "33" * 32)
    assert code == dc.EXIT_FAILED, (code, probe)
    print("PASS consensus canceled → EXIT_FAILED")


def test_processing_at_budget():
    store = base_store()
    store["tx_seq"] = [store["tx_seq"][1]]
    store["receipt_seq"] = [make_receipt()]
    store["consensus_seq"] = [{"lifecycle": {"state": "processing", "phase": "accepted — appeal window"}}]
    code, probe = follow(store, "0x" + "44" * 32, args_for(finality_timeout=0.5))
    assert code == dc.EXIT_PROCESSING, (code, probe)
    print("PASS still processing at budget → EXIT_PROCESSING")


def test_mined_without_consensus_event():
    store = base_store()
    store["tx_seq"] = [store["tx_seq"][1]]
    store["receipt_seq"] = [{"status": 1, "blockNumber": 21521500, "logs": []}]
    code, probe = follow(store, "0x" + "55" * 32)
    assert code == dc.EXIT_FAILED, (code, probe)
    print("PASS mined without consensus event → EXIT_FAILED")


def test_evm_reverted():
    store = base_store()
    store["tx_seq"] = [store["tx_seq"][1]]
    store["receipt_seq"] = [make_receipt(status=0)]
    code, probe = follow(store, "0x" + "66" * 32)
    assert code == dc.EXIT_FAILED, (code, probe)
    assert probe["state"] == dc.STATUS_FAILED
    print("PASS EVM reverted → EXIT_FAILED")


def test_superseded():
    store = {
        "tx_seq": [{"from": "0x" + "11" * 20, "nonce": 6, "blockNumber": None}],
        "receipt_seq": [None],
        "nonce_seq": [9],
        "pending_seq": [9],
        "consensus_seq": [],
        "calls": {"tx": 0, "rcpt": 0, "nonce": 0},
    }
    code, probe = follow(store, "0x" + "77" * 32)
    assert code == dc.EXIT_FAILED, (code, probe)
    assert probe["state"] == dc.STATUS_SUPERSEDED
    print("PASS superseded nonce → EXIT_FAILED/SUPERSEDED")


def test_unreadable_consensus_record():
    store = base_store()
    client = FakeClient(store)

    def boom(tx_id=None):
        raise RuntimeError("execution reverted: no such transaction")

    client.get_transaction = boom
    probe = dc.probe_consensus(client, "0x" + "ee" * 32)
    assert probe["state"] == dc.STATUS_UNKNOWN, probe
    print("PASS unreadable consensus record → UNKNOWN detail:", probe["detail"])


def test_unknown_with_known_sender_unfunded():
    store = base_store()
    store["tx_seq"] = [None]  # envelope gone
    client = FakeClient(store)
    # poor account: balance below gas price x deploy-size gas limit (5e15 wei)
    client.w3.eth.get_balance = lambda a: 10 ** 15  # 0.001 GEN
    probe = dc.probe_envelope(client, "0x" + "22" * 32, sender="0x" + "ab" * 20)
    assert probe["state"] == dc.STATUS_UNKNOWN
    assert probe["nonce_latest"] == 7 and probe["balance"] == 10 ** 15, probe
    lines = dc.envelope_diagnostics(probe)
    assert any("account nonce" in line for line in lines), lines
    assert any("balance" in line for line in lines), lines
    cause = dc.likely_dropped_cause(probe)
    assert "lack of funds" in cause, cause
    print("PASS UNKNOWN + known sender → account diagnostics + funds cause")


def test_unknown_with_known_sender_gas_starved():
    store = base_store()
    store["tx_seq"] = [None]
    store["gas_price"] = 5 * 10 ** 9  # base fee 0 → sdk max fee 2 gwei < 5 gwei
    client = FakeClient(store)
    client.w3.eth.get_balance = lambda a: 10 ** 19  # well funded
    probe = dc.probe_envelope(client, "0x" + "22" * 32, sender="0x" + "ab" * 20)
    assert probe["state"] == dc.STATUS_UNKNOWN
    cause = dc.likely_dropped_cause(probe)
    assert "maxFeePerGas" in cause and "gas price" in cause, cause
    print("PASS UNKNOWN + funded sender + high gas price → fee-starvation cause")


def test_created_transaction_event():
    from web3 import Web3 as W

    created_topic = W().keccak(text="CreatedTransaction(bytes32,uint256)")
    receipt = {"status": 1, "blockNumber": 1, "logs": [{
        "address": CONSENSUS,
        "topics": [created_topic, Web3.to_bytes(hexstr=TXID), Web3.to_bytes(hexstr="0x01")],
    }]}
    got = dc.consensus_tx_id_from_receipt(Web3(), receipt, CONSENSUS.lower())
    assert got == TXID, got
    print("PASS CreatedTransaction event decoded")


def test_finalized_with_bad_execution_result():
    store = base_store()
    store["tx_seq"] = [store["tx_seq"][1]]
    store["receipt_seq"] = [make_receipt()]
    store["consensus_seq"] = [
        {"lifecycle": {"state": "finalized", "outcome": "accepted"},
         "data": {"contract_address": "0x" + "aa" * 20},
         "tx_execution_result_name": "FINISHED_WITH_ERROR"}
    ]
    code, probe = follow(store, "0x" + "88" * 32)
    assert code == dc.EXIT_FAILED, (code, probe)
    print("PASS finalized but FINISHED_WITH_ERROR → EXIT_FAILED")


def main():
    test_pending_to_mined_to_finalized()
    test_unknown_dropped()
    test_canceled()
    test_processing_at_budget()
    test_mined_without_consensus_event()
    test_evm_reverted()
    test_superseded()
    test_unreadable_consensus_record()
    test_unknown_with_known_sender_unfunded()
    test_unknown_with_known_sender_gas_starved()
    test_created_transaction_event()
    test_finalized_with_bad_execution_result()
    print("\nALL DEPLOY-TRACKING TESTS PASSED")


if __name__ == "__main__":
    main()
