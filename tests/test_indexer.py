"""The indexer mirrors the contract. It must never outrank it."""

from __future__ import annotations

import pytest

from services.indexer.indexer import Indexer
from services.lib.genlayer.client import get_registry, reset
from services.lib.genlayer.config import GenLayerConfig


@pytest.fixture()
def seeded(monkeypatch, tmp_path):
    monkeypatch.setenv("GENLAYER_NETWORK", "demo")
    reset()
    registry = get_registry(GenLayerConfig.from_env())
    chain = get_registry(GenLayerConfig.from_env()).chain
    for index, facts in enumerate(
        [
            [
                "Digital service purchased 14 days before cancellation",
                "Approximately 40% of the entitlement consumed",
                "No usage-based exclusion in the purchase terms",
            ],
            [
                "Monthly recurring plan, cancelled 14 days into the billing cycle",
                "Approximately 40% of the cycle entitlement consumed",
                "No usage-based exclusion in the plan terms",
            ],
            [
                "Digital service purchased 12 days before cancellation",
                "The service was fully delivered before cancellation",
                "No usage-based exclusion in the purchase terms",
            ],
        ],
        start=1,
    ):
        case_id = f"CASE-00{index}"
        registry.submit_case(case_id, facts, sender=registry.adjudicator_address)
        written = registry.adjudicate(case_id, sender=registry.adjudicator_address)
        chain.settle(written.transaction_reference)
    yield registry, tmp_path
    reset()


def test_indexer_mirrors_holdings_citations_and_cases(seeded):
    registry, tmp_path = seeded
    indexer = Indexer(GenLayerConfig.from_env(), db_path=tmp_path / "index.db")
    result = indexer.run_once()

    assert result.holdings == 3
    assert result.new_holdings == ["HLD-000001", "HLD-000002", "HLD-000003"]
    assert len(result.newly_final) == 3

    rows = indexer.connection.execute("SELECT * FROM holdings ORDER BY holding_id").fetchall()
    assert [row["holding_id"] for row in rows] == ["HLD-000001", "HLD-000002", "HLD-000003"]
    assert all(row["status"] == "FINAL" for row in rows)
    assert all(row["holding_hash"].startswith("0x") for row in rows)

    edges = indexer.connection.execute("SELECT * FROM citations").fetchall()
    assert {(row["source_holding_id"], row["relationship"]) for row in edges} == {
        ("HLD-000002", "FOLLOWS"),
        ("HLD-000003", "DISTINGUISHES"),
    }

    cases = indexer.connection.execute("SELECT * FROM cases ORDER BY case_id").fetchall()
    assert [row["holding_id"] for row in cases] == ["HLD-000001", "HLD-000002", "HLD-000003"]
    indexer.close()


def test_provenance_lookup_answers_where_a_holding_came_from(seeded):
    registry, tmp_path = seeded
    indexer = Indexer(GenLayerConfig.from_env(), db_path=tmp_path / "index.db")
    indexer.run_once()

    provenance = indexer.provenance("HLD-000001")
    assert provenance["case_id"] == "CASE-001"
    assert provenance["source_contract"].startswith("0xDEMO")
    assert provenance["source_tx"].startswith("0xdef1")
    assert provenance["holding_hash"].startswith("0x")
    assert provenance["simulated"] is True
    assert "canonical" in provenance["note"]
    assert indexer.provenance("HLD-999999") is None
    indexer.close()


def test_text_fallback_search(seeded):
    registry, tmp_path = seeded
    indexer = Indexer(GenLayerConfig.from_env(), db_path=tmp_path / "index.db")
    indexer.run_once()

    assert indexer.search_text("fully delivered") != []
    assert indexer.search_text("fully delivered", domain="other") == []
    assert indexer.search_text("zzzz-nothing") == []
    indexer.close()


def test_the_index_refreshes_when_the_contract_changes(seeded):
    """The contract wins: the index follows it, never the other way round."""
    registry, tmp_path = seeded
    indexer = Indexer(GenLayerConfig.from_env(), db_path=tmp_path / "index.db")
    indexer.run_once()

    owner = "0x1111111111111111111111111111111111111111"
    created = registry.create_holding(
        case_id="CASE-777",
        source_tx="0x" + "77" * 32,
        domain="digital-commerce",
        contract_class="RefundArbiter",
        issue="Refund eligibility after partial consumption of a digital service",
        facts_digest="purchased 14 days before cancellation, 40% consumed, no exclusion",
        verdict="APPROVED",
        ratio="Where a digital service is partly consumed and no exclusion applies, a pro rata refund is owed.",
        reason_codes=["PARTIAL_CONSUMPTION"],
        evidence_hashes=[],
        panel_size=5,
        sender=owner,
    )
    holding_id = "HLD-000004"
    indexer.run_once()
    assert indexer.connection.execute(
        "SELECT status FROM holdings WHERE holding_id = ?", (holding_id,)
    ).fetchone()["status"] == "UNVERIFIED"

    registry.reject_holding(holding_id=holding_id, reason="Withdrawn by the operator", sender=owner)
    indexer.run_once()

    row = indexer.connection.execute("SELECT status FROM holdings WHERE holding_id = ?", (holding_id,)).fetchone()
    assert row["status"] == "REJECTED"
    assert registry.get_holding(holding_id).status == "REJECTED"
    indexer.close()
