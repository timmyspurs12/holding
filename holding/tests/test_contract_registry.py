"""HoldingRegistry contract logic: lifecycle, authority, cold start, graph.

Executed against the runtime stub — see tests/stubs/genlayer.py.
"""

from __future__ import annotations

import pytest

import genlayer

from tests.conftest import (
    ADJUDICATOR_ADDRESS,
    ATTESTOR,
    OWNER,
    SOURCE,
    STRANGER,
    as_sender,
    make_final,
)

FACTS = "Digital service purchased 14 days before cancellation. 40% consumed."
GOOD = dict(
    case_id="CASE-0184",
    source_tx="0xaaa111",
    domain="digital-commerce",
    contract_class="RefundArbiter",
    issue="Refund eligibility after partial service consumption",
    facts_digest=FACTS,
    verdict="APPROVED",
    ratio="Where a digital service is partially consumed and no usage exclusion exists, a pro rata refund is owed.",
    reason_codes=["PARTIAL_CONSUMPTION"],
    evidence_hashes=["0x9f2ac41d"],
    panel_size=5,
)


def submit(registry, **overrides):
    payload = dict(GOOD)
    payload.update(overrides)
    with as_sender(ADJUDICATOR_ADDRESS):
        return registry.create_holding(**payload)


# ---------------------------------------------------------------------------
# creation
# ---------------------------------------------------------------------------
def test_create_holding_starts_non_final(registry):
    holding_id = submit(registry)
    assert holding_id == "HLD-000001"
    record = registry.get_holding(holding_id)
    assert record["status"] == "PENDING"          # registered source contract
    assert record["authority_bp"] < 7_500
    assert record["holding_id"].startswith("HLD-")


def test_manual_submission_is_unverified(registry):
    with as_sender(OWNER):
        holding_id = registry.create_holding(**GOOD)
    assert registry.get_holding(holding_id)["status"] == "UNVERIFIED"


def test_unregistered_caller_cannot_create(registry):
    with as_sender(STRANGER):
        with pytest.raises(genlayer.UserError):
            registry.create_holding(**GOOD)


def test_duplicate_case_is_rejected(registry):
    submit(registry)
    with as_sender(ADJUDICATOR_ADDRESS):
        with pytest.raises(genlayer.UserError):
            registry.create_holding(**GOOD)


@pytest.mark.parametrize(
    "field,value",
    [
        ("verdict", "MAYBE"),
        ("issue", "short"),
        ("ratio", "too short"),
        ("facts_digest", "x"),
        ("panel_size", 0),
    ],
)
def test_malformed_payloads_are_rejected(registry, field, value):
    with as_sender(ADJUDICATOR_ADDRESS):
        with pytest.raises(genlayer.UserError):
            submit(registry, **{field: value})


def test_ids_are_sequential(registry):
    first = submit(registry)
    second = submit(registry, case_id="CASE-0185", source_tx="0xaaa112")
    assert (first, second) == ("HLD-000001", "HLD-000002")


# ---------------------------------------------------------------------------
# finality
# ---------------------------------------------------------------------------
def test_accepted_is_not_final(registry):
    """Consensus v0.6: status 5 (Accepted) must not produce a final holding."""
    holding_id = submit(registry)
    with as_sender(ATTESTOR):
        status = registry.attest_finality(holding_id, 5, "FINISHED_WITH_RETURN", 1_770_000_000)
    assert status == "REJECTED"
    assert registry.get_holding(holding_id)["status"] == "REJECTED"


def test_finalized_with_failed_execution_is_rejected(registry):
    holding_id = submit(registry)
    with as_sender(ATTESTOR):
        status = registry.attest_finality(holding_id, 7, "ERROR", 1_770_000_000)
    assert status == "REJECTED"


def test_finality_requires_attestor(registry):
    holding_id = submit(registry)
    with as_sender(STRANGER):
        with pytest.raises(genlayer.UserError):
            registry.attest_finality(holding_id, 7, "FINISHED_WITH_RETURN", 1_770_000_000)


def test_attestation_records_provenance(registry):
    holding_id = submit(registry)
    make_final(registry, holding_id, appeal_outcome="UPHELD", source_tx="0xdeadbeef")
    record = registry.get_holding(holding_id)
    assert record["status"] == "FINAL"
    assert record["tx_status_code"] == 7
    assert record["execution_result"] == "FINISHED_WITH_RETURN"
    assert record["finality_timestamp"] == 1_770_000_000
    assert record["source_tx"] == "0xaaa111"   # original value is not overwritten
    assert record["source_contract"] == ADJUDICATOR_ADDRESS


def test_final_holding_cannot_be_re_attested(registry):
    holding_id = submit(registry)
    make_final(registry, holding_id)
    with as_sender(ATTESTOR):
        with pytest.raises(genlayer.UserError):
            registry.attest_finality(holding_id, 7, "FINISHED_WITH_RETURN", 1_770_000_100)


# ---------------------------------------------------------------------------
# cold start + retrieval
# ---------------------------------------------------------------------------
def test_cold_start_returns_empty_list(registry):
    assert registry.get_precedent(FACTS, "digital-commerce", 3) == []


def test_empty_digest_returns_empty_list(registry):
    assert registry.get_precedent("   ", "digital-commerce", 3) == []


def test_pending_holdings_are_not_precedent(registry):
    submit(registry)
    assert registry.get_precedent(FACTS, "digital-commerce", 3) == []


def test_final_holding_is_retrievable(registry):
    holding_id = submit(registry)
    make_final(registry, holding_id)
    results = registry.get_precedent(FACTS, "digital-commerce", 3)
    assert len(results) == 1
    assert results[0]["holding_id"] == holding_id
    assert results[0]["status"] == "FINAL"
    assert 0.0 <= float(results[0]["similarity"]) <= 1.0


def test_domain_filter_is_applied(registry):
    holding_id = submit(registry)
    make_final(registry, holding_id)
    assert registry.get_precedent(FACTS, "insurance-claims", 3) == []
    assert len(registry.get_precedent(FACTS, "all", 3)) == 1


def test_k_is_clamped(registry):
    for index in range(4):
        holding_id = submit(registry, case_id=f"CASE-{index}", source_tx=f"0xaaa11{index}")
        make_final(registry, holding_id)
    assert len(registry.get_precedent(FACTS, "digital-commerce", 99)) <= 10
    assert len(registry.get_precedent(FACTS, "digital-commerce", 0)) == 1


def test_retrieval_order_is_deterministic(registry):
    for index in range(3):
        holding_id = submit(registry, case_id=f"CASE-{index}", source_tx=f"0xaaa11{index}")
        make_final(registry, holding_id)
    first = registry.get_precedent(FACTS, "digital-commerce", 3)
    second = registry.get_precedent(FACTS, "digital-commerce", 3)
    assert [item["holding_id"] for item in first] == [item["holding_id"] for item in second]
    similarities = [float(item["similarity"]) for item in first]
    assert similarities == sorted(similarities, reverse=True)


# ---------------------------------------------------------------------------
# authority
# ---------------------------------------------------------------------------
def test_authority_increases_with_finality(registry):
    holding_id = submit(registry)
    before = registry.get_holding(holding_id)["authority_bp"]
    make_final(registry, holding_id)
    after = registry.get_holding(holding_id)["authority_bp"]
    assert after > before


def test_authority_rewards_appeal_survival(registry):
    upheld = submit(registry, case_id="CASE-A", source_tx="0xa1")
    overturned = submit(registry, case_id="CASE-B", source_tx="0xa2")
    make_final(registry, upheld, appeal_outcome="UPHELD")
    make_final(registry, overturned, appeal_outcome="OVERTURNED")
    assert registry.get_holding(upheld)["authority_bp"] > registry.get_holding(overturned)["authority_bp"]


def test_authority_rewards_panel_size(registry):
    small = submit(registry, case_id="CASE-C", source_tx="0xa3", panel_size=5)
    large = submit(registry, case_id="CASE-D", source_tx="0xa4", panel_size=11)
    make_final(registry, small)
    make_final(registry, large)
    assert registry.get_holding(large)["authority_bp"] > registry.get_holding(small)["authority_bp"]


def test_citation_raises_target_authority(registry):
    first = submit(registry, case_id="CASE-E", source_tx="0xa5")
    second = submit(registry, case_id="CASE-F", source_tx="0xa6")
    make_final(registry, first)
    make_final(registry, second)
    before = registry.get_holding(first)["authority_bp"]
    with as_sender(ADJUDICATOR_ADDRESS):
        registry.cite(second, first, "FOLLOWS", "CASE-F")
    after = registry.get_holding(first)["authority_bp"]
    assert after > before
    assert registry.get_holding(first)["citation_count"] == 1
    assert registry.get_holding(first)["followed_count"] == 1


# ---------------------------------------------------------------------------
# citation graph
# ---------------------------------------------------------------------------
def test_only_final_holdings_may_cite(registry):
    first = submit(registry, case_id="CASE-G", source_tx="0xa7")
    second = submit(registry, case_id="CASE-H", source_tx="0xa8")
    make_final(registry, first)
    with as_sender(ADJUDICATOR_ADDRESS):
        with pytest.raises(genlayer.UserError):
            registry.cite(second, first, "FOLLOWS", "CASE-H")


def test_citation_requires_known_holdings(registry):
    first = submit(registry, case_id="CASE-I", source_tx="0xa9")
    make_final(registry, first)
    with as_sender(ADJUDICATOR_ADDRESS):
        with pytest.raises(genlayer.UserError):
            registry.cite(first, "HLD-999999", "FOLLOWS", "CASE-I")


def test_self_citation_rejected(registry):
    first = submit(registry, case_id="CASE-J", source_tx="0xb1")
    make_final(registry, first)
    with as_sender(ADJUDICATOR_ADDRESS):
        with pytest.raises(genlayer.UserError):
            registry.cite(first, first, "FOLLOWS", "CASE-J")


def test_unsupported_relationship_rejected(registry):
    first = submit(registry, case_id="CASE-K", source_tx="0xb2")
    second = submit(registry, case_id="CASE-L", source_tx="0xb3")
    make_final(registry, first)
    make_final(registry, second)
    with as_sender(ADJUDICATOR_ADDRESS):
        with pytest.raises(genlayer.UserError):
            registry.cite(second, first, "OVERRULES", "CASE-L")


def test_duplicate_citation_is_idempotent(registry):
    first = submit(registry, case_id="CASE-M", source_tx="0xb4")
    second = submit(registry, case_id="CASE-N", source_tx="0xb5")
    make_final(registry, first)
    make_final(registry, second)
    with as_sender(ADJUDICATOR_ADDRESS):
        assert registry.cite(second, first, "FOLLOWS", "CASE-N") is True
        assert registry.cite(second, first, "FOLLOWS", "CASE-N") is False
    assert registry.get_holding(first)["citation_count"] == 1


def test_distinguishment_is_recorded_against_the_target(registry):
    first = submit(registry, case_id="CASE-O", source_tx="0xb6")
    second = submit(registry, case_id="CASE-P", source_tx="0xb7")
    make_final(registry, first)
    make_final(registry, second)
    with as_sender(ADJUDICATOR_ADDRESS):
        registry.cite(second, first, "DISTINGUISHES", "CASE-P")
    assert registry.get_holding(first)["distinguishment_count"] == 1
    assert registry.get_distinguishments(first)[0]["holding_id"] == second


def test_cite_by_case_parks_intent_until_the_holding_exists(registry):
    target = submit(registry, case_id="CASE-Q", source_tx="0xb8")
    make_final(registry, target)
    with as_sender(ADJUDICATOR_ADDRESS):
        assert registry.cite_by_case("CASE-0184", target, "FOLLOWS", "CASE-0184") is False
    # the holding for CASE-0184 does not exist yet — intent is parked
    assert registry.get_holding(target)["citation_count"] == 0
    holding_id = submit(registry)
    make_final(registry, holding_id)
    with as_sender(ADJUDICATOR_ADDRESS):
        registry.cite(holding_id, target, "FOLLOWS", "CASE-0184")
    assert registry.get_holding(target)["citation_count"] == 1


# ---------------------------------------------------------------------------
# admin + views
# ---------------------------------------------------------------------------
def test_only_owner_registers_sources(registry):
    with as_sender(STRANGER):
        with pytest.raises(genlayer.UserError):
            registry.register_source(SOURCE, True)
    with as_sender(OWNER):
        registry.register_source(SOURCE, True)
    assert registry.is_registered_source(SOURCE) is True


def test_reject_holding_blocks_precedent_use(registry):
    holding_id = submit(registry)
    with as_sender(ATTESTOR):
        registry.reject_holding(holding_id, "finality attestation failed")
    assert registry.get_holding(holding_id)["status"] == "REJECTED"
    assert registry.get_precedent(FACTS, "digital-commerce", 3) == []


def test_stats_and_listing(registry):
    first = submit(registry)
    second = submit(registry, case_id="CASE-R", source_tx="0xb9")
    make_final(registry, first)
    stats = registry.get_stats()
    assert stats["total"] == 2
    assert stats["final"] == 1
    assert stats["pending"] == 1
    assert stats["embedding_model"] == "all-MiniLM-L6-v2"
    assert len(registry.get_holdings(limit=10)) == 2
    assert len(registry.get_holdings(limit=1)) == 1


def test_unknown_holding_returns_empty(registry):
    assert registry.get_holding("HLD-999999") == {}
