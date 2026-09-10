"""Unit tests for the deterministic core shared by the contract, the indexer and
the Reporter API: schema, authority, precedent ranking and validation."""

from __future__ import annotations

import pytest

from shared.holding_core import authority, precedent, schema, validation
from shared.holding_core._mirrored import (
    compute_authority_bp,
    compute_components,
    normalize_for_embedding,
    similarity_to_bp,
)


def rec(holding_id, similarity="0.90", domain="digital-commerce", status="FINAL", authority_bp=6000):
    return {
        "holding_id": holding_id,
        "domain": domain,
        "status": status,
        "similarity": similarity,
        "authority_bp": authority_bp,
    }


# ---------------------------------------------------------------------------
# authority
# ---------------------------------------------------------------------------
def test_authority_is_deterministic_and_bounded():
    a = authority.compute_authority("FINAL", "UPHELD", 11, 9, 6, 1)
    b = authority.compute_authority("FINAL", "UPHELD", 11, 9, 6, 1)
    assert a == b
    assert 0 <= a["score_bp"] <= 10_000
    assert abs(a["score"] - a["score_bp"] / 10_000) < 1e-9


def test_authority_rises_with_finality_appeals_panel_and_citations():
    pending = authority.compute_authority("PENDING")["score_bp"]
    final = authority.compute_authority("FINAL")["score_bp"]
    rejected = authority.compute_authority("REJECTED")["score_bp"]
    assert pending < final
    assert rejected < pending

    assert authority.compute_authority("FINAL", "UPHELD")["score_bp"] > authority.compute_authority("FINAL", "OVERTURNED")["score_bp"]
    assert authority.compute_authority("FINAL", "NONE", 11)["score_bp"] > authority.compute_authority("FINAL", "NONE", 5)["score_bp"]
    assert authority.compute_authority("FINAL", "NONE", 5, 9)["score_bp"] > authority.compute_authority("FINAL", "NONE", 5, 1)["score_bp"]


def test_authority_rewards_being_followed_over_being_distinguished():
    followed = authority.compute_authority("FINAL", "NONE", 5, 0, 8, 2)
    distinguished = authority.compute_authority("FINAL", "NONE", 5, 0, 2, 8)
    assert followed["score_bp"] > distinguished["score_bp"]


def test_authority_components_are_exposed_and_explainable():
    result = authority.compute_authority("FINAL", "UPHELD", 7, 4, 3, 1)
    assert set(result["components_bp"]) == {"finality", "appeal", "panel", "citations", "consistency"}
    assert sum(result["weights_bp"].values()) == 10_000
    assert {row["component"] for row in result["breakdown"]} == set(result["components_bp"])
    assert all(row["meaning"] for row in result["breakdown"])
    assert "Authority" in result["explanation"]
    assert result["formula"]


def test_authority_components_saturate_rather_than_run_away():
    assert compute_components("FINAL", "NONE", 999, 10_000, 0, 0)["panel"] <= 10_000
    assert compute_components("FINAL", "NONE", 5, 10_000, 0, 0)["citations"] == 10_000
    assert compute_authority_bp(compute_components("FINAL", "NONE", 999, 10_000, 0, 0)) <= 10_000


def test_bands():
    assert authority.band(9_000) == "HIGH"
    assert authority.band(5_000) == "MODERATE"
    assert authority.band(100) == "DEVELOPING"


# ---------------------------------------------------------------------------
# similarity plumbing (floats must not leak into contract state)
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("value,expected", [("0.8734", 8734), (0.5, 5000), ("1", 10000), ("0", 0)])
def test_similarity_is_integer_basis_points(value, expected):
    assert similarity_to_bp(value) == expected


def test_normalisation_is_stable():
    """Embedding text must be identical for cosmetic differences in input."""
    assert normalize_for_embedding("  Refund   Eligibility ") == normalize_for_embedding("refund eligibility")
    assert normalize_for_embedding("REFUND eligibility") == normalize_for_embedding("refund eligibility")
    assert normalize_for_embedding("Refund eligibility!") == normalize_for_embedding("Refund eligibility")


# ---------------------------------------------------------------------------
# ranking
# ---------------------------------------------------------------------------
def test_ranking_prefers_same_domain_then_similarity_then_authority():
    ranked = precedent.rank_precedents(
        [
            rec("HLD-000003", "0.95", domain="other-domain"),
            rec("HLD-000001", "0.80"),
            rec("HLD-000002", "0.80", authority_bp=9000),
        ],
        k=3,
        domain="digital-commerce",
    )
    assert [r["holding_id"] for r in ranked] == ["HLD-000002", "HLD-000001", "HLD-000003"]


def test_ranking_excludes_anything_that_is_not_final():
    ranked = precedent.rank_precedents([rec("HLD-000001", status="PENDING"), rec("HLD-000002", status="UNVERIFIED")], k=3)
    assert ranked == []


def test_ranking_respects_k_and_caps_it():
    many = [rec(f"HLD-{i:06d}", f"0.{90 - i % 10}") for i in range(1, 40)]
    assert len(precedent.rank_precedents(many, k=3)) == 3
    assert len(precedent.rank_precedents(many, k=999)) == precedent.MAX_K
    assert len(precedent.rank_precedents(many, k=0)) == 1


def test_cold_start_ranking_returns_empty():
    assert precedent.rank_precedents([], k=3, domain="digital-commerce") == []


# ---------------------------------------------------------------------------
# validation
# ---------------------------------------------------------------------------
VALID = dict(
    case_id="CASE-001",
    domain="digital-commerce",
    contract_class="RefundArbiter",
    issue="Whether a pro rata refund is owed after partial consumption",
    facts_digest="service 14d, 40% consumed, no exclusion",
    verdict="APPROVED",
    ratio="Where a digital service is partly consumed and no exclusion applies, a pro rata refund is owed.",
    panel_size=5,
    reason_codes=["PARTIAL_CONSUMPTION"],
    evidence_hashes=["0x" + "ab" * 32],
)


def test_valid_payload_passes():
    assert validation.validate_holding_creation(**VALID)["verdict"] == "APPROVED"


@pytest.mark.parametrize(
    "field,value",
    [
        ("verdict", "MAYBE"),
        ("domain", "!!!"),
        ("issue", "no"),
        ("ratio", "ok"),
        ("panel_size", 0),
        ("panel_size", "many"),
        ("case_id", ""),
        ("source_tx", "not-hex"),
    ],
)
def test_malformed_payloads_are_rejected(field, value):
    payload = dict(VALID, **{field: value})
    with pytest.raises(validation.ValidationError):
        validation.validate_holding_creation(**payload)


def test_reason_codes_and_evidence_are_shape_checked():
    with pytest.raises(validation.ValidationError):
        validation.validate_holding_creation(**dict(VALID, reason_codes=["lower case"]))
    with pytest.raises(validation.ValidationError):
        validation.validate_holding_creation(**dict(VALID, evidence_hashes=["0xzz"]))


def test_distinguishment_must_be_a_concrete_material_difference():
    good = "Unlike the cited holding, the service was fully delivered before cancellation."
    assert validation.validate_distinguishment(good, required=True)[0] == good
    for bad in ["The circumstances differ.", "This case is different.", "n/a", "short", ""]:
        text, errors = validation.validate_distinguishment(bad, required=True)
        assert errors, bad


def test_optional_distinguishment_may_be_empty():
    assert validation.validate_distinguishment("", required=False) == ("", [])


def test_finality_attestation_rules():
    assert validation.is_finality_attestation_valid(7, "FINISHED_WITH_RETURN")
    assert not validation.is_finality_attestation_valid(5, "FINISHED_WITH_RETURN")
    assert not validation.is_finality_attestation_valid(7, "FINISHED_WITH_ERROR")


def test_relationship_validation():
    known = ["HLD-000001", "HLD-000002"]
    assert validation.validate_relationship("HLD-000001", "HLD-000002", "FOLLOWS", known) == []
    assert validation.validate_relationship("HLD-000001", "HLD-000001", "FOLLOWS", known)
    assert validation.validate_relationship("HLD-000001", "HLD-000002", "LOVES", known)
    assert validation.validate_relationship("HLD-000001", "HLD-000009", "FOLLOWS", known)
    assert validation.validate_relationship("nope", "HLD-000002", "FOLLOWS", known)


# ---------------------------------------------------------------------------
# schema / provenance
# ---------------------------------------------------------------------------
def test_holding_ids_are_canonical():
    assert schema.make_holding_id(1) == "HLD-000001"
    assert schema.holding_id_sequence("HLD-000042") == 42
    assert schema.is_valid_holding_id("HLD-000001")
    assert not schema.is_valid_holding_id("HLD-1")


def test_holding_hash_changes_with_content_and_is_stable():
    fields = {"case_id": "CASE-001", "verdict": "APPROVED", "ratio": "r", "domain": "digital-commerce"}
    assert schema.holding_hash(fields) == schema.holding_hash(fields)
    assert schema.holding_hash(fields) != schema.holding_hash(dict(fields, verdict="REJECTED"))


def test_canonical_holding_contains_the_provenance_chain():
    record = schema.canonical_holding(
        {
            "holding_id": "HLD-000001",
            "case_id": "CASE-001",
            "domain": "digital-commerce",
            "contract_address": "0xabc",
            "transaction_reference": "0xdef",
            "status": "FINAL",
            "finality_timestamp": 1_770_000_000,
            "evidence_hashes": ["0x" + "11" * 32],
            "authority_bp": 6200,
        }
    )
    for key in ("holding_id", "case_id", "contract_address", "transaction_reference", "status", "finality_timestamp", "evidence_hashes"):
        assert key in record


def test_adjudication_payload_contract_rejects_missing_keys():
    with pytest.raises(validation.ValidationError):
        validation.validate_adjudication_payload({"verdict": "APPROVED"})
    ok = validation.validate_adjudication_payload(
        {
            "issue": "Refund eligibility after partial consumption of a digital service",
            "facts": ["purchased 14 days before cancellation", "40% consumed"],
            "verdict": "APPROVED",
            "ratio": "Pro rata refund owed where consumption is partial and no exclusion applies.",
            "reason_codes": ["PARTIAL_CONSUMPTION"],
        }
    )
    assert ok["verdict"] == "APPROVED"
