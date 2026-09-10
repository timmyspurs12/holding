"""The product loop, executed against the contract logic.

CASE -> ADJUDICATION -> FINALITY -> HOLDING -> INDEX ->
PRECEDENT RETRIEVAL -> FOLLOW OR DISTINGUISH -> NEW HOLDING

See tests/stubs/genlayer.py for what the stub does and does not model.
"""

from __future__ import annotations

import pytest

import genlayer

from tests.conftest import (
    ADJUDICATOR_ADDRESS,
    as_sender,
    emitted,
    make_final,
    replay,
    stub_llm_response,
)

CASE_A_FACTS = [
    "Digital service purchased 14 days before cancellation",
    "Approximately 40% of the entitlement consumed",
    "No usage-based exclusion in the purchase terms",
]
CASE_B_FACTS = [
    "Monthly recurring plan, cancelled 14 days into the billing cycle",
    "Approximately 40% of the cycle entitlement consumed",
    "No usage-based exclusion in the plan terms",
]
CASE_C_FACTS = [
    "Digital service purchased 12 days before cancellation",
    "The service was fully delivered before cancellation",
    "No usage-based exclusion in the purchase terms",
]

GOOD_REASON = (
    "Unlike Holding #00184, the service was already fully delivered before cancellation, "
    "so the partial-consumption rule does not apply."
)


def llm(verdict="APPROVED", used=None, distinguished=False, reason=""):
    return {
        "issue": "Refund eligibility after partial service consumption",
        "facts": ["material fact one", "material fact two"],
        "verdict": verdict,
        "ratio": "Where a digital service is partially consumed and no exclusion applies, a pro rata refund is owed.",
        "reason_codes": ["PARTIAL_CONSUMPTION"],
        "precedent_used": used or [],
        "followed": not distinguished,
        "distinguished": distinguished,
        "distinguishment_reason": reason,
        "reasoning": "The nearest holding governs these facts.",
    }


# ---------------------------------------------------------------------------
# submission + adjudication
# ---------------------------------------------------------------------------
def test_case_lifecycle_starts_at_proposed(adjudicator):
    with as_sender(ADJUDICATOR_ADDRESS):
        adjudicator.submit_case("CASE-A", CASE_A_FACTS)
    record = adjudicator.get_case("CASE-A")
    assert record["status"] == "PROPOSED"
    assert record["facts"] == CASE_A_FACTS


def test_duplicate_case_rejected(adjudicator):
    with as_sender(ADJUDICATOR_ADDRESS):
        adjudicator.submit_case("CASE-A", CASE_A_FACTS)
        with pytest.raises(genlayer.UserError):
            adjudicator.submit_case("CASE-A", CASE_A_FACTS)


def test_empty_facts_rejected(adjudicator):
    with as_sender(ADJUDICATOR_ADDRESS):
        with pytest.raises(genlayer.UserError):
            adjudicator.submit_case("CASE-EMPTY", [])


def test_malformed_model_output_is_rejected(adjudicator):
    stub_llm_response({"verdict": "MAYBE", "issue": "x", "ratio": "nope"})
    with as_sender(ADJUDICATOR_ADDRESS):
        adjudicator.submit_case("CASE-BAD", CASE_A_FACTS)
        with pytest.raises(genlayer.UserError):
            adjudicator.adjudicate("CASE-BAD")
    # a failed validation round leaves the case retryable, not advanced
    assert adjudicator.get_case("CASE-BAD")["status"] == "VALIDATING"
    assert adjudicator.get_case("CASE-BAD")["verdict"] == ""


# ---------------------------------------------------------------------------
# STEP 1-2 · cold start: no precedent, holding still created on finalization
# ---------------------------------------------------------------------------
def test_cold_start_creates_first_holding(registry, adjudicator):
    stub_llm_response(llm())
    with as_sender(ADJUDICATOR_ADDRESS):
        adjudicator.submit_case("CASE-A", CASE_A_FACTS)
        assert adjudicator.adjudicate("CASE-A") == "APPEAL_WINDOW"

    # retrieval happened, but the registry was empty
    assert registry.get_stats()["total"] == 0

    # the holding is only created when the transaction finalizes
    final_calls = emitted("finalized")
    assert [c["method"] for c in final_calls] == ["create_holding"]
    assert final_calls[0]["args"][0] == "CASE-A"

    replay(sender=ADJUDICATOR_ADDRESS)
    assert registry.get_stats()["total"] == 1
    holding_id = registry.get_holdings()[0]["holding_id"]
    assert registry.get_holding(holding_id)["status"] == "PENDING"

    make_final(registry, holding_id)
    assert registry.get_precedent(" ".join(CASE_A_FACTS), "digital-commerce", 3)[0]["holding_id"] == holding_id


def test_holding_is_never_emitted_on_acceptance(registry, adjudicator):
    """A leader proposing a verdict must not create a holding."""
    stub_llm_response(llm())
    with as_sender(ADJUDICATOR_ADDRESS):
        adjudicator.submit_case("CASE-A", CASE_A_FACTS)
        adjudicator.adjudicate("CASE-A")
    assert emitted("accepted") == []
    assert len(emitted("finalized")) == 1


# ---------------------------------------------------------------------------
# STEP 3-4 · follow
# ---------------------------------------------------------------------------
def test_panel_follows_retrieved_precedent(registry, adjudicator):
    # seed: a final holding exists
    stub_llm_response(llm())
    with as_sender(ADJUDICATOR_ADDRESS):
        adjudicator.submit_case("CASE-A", CASE_A_FACTS)
        adjudicator.adjudicate("CASE-A")
    replay(sender=ADJUDICATOR_ADDRESS)
    first = registry.get_holdings()[0]["holding_id"]
    make_final(registry, first)

    # new, materially similar case
    stub_llm_response(llm(used=[first]))
    with as_sender(ADJUDICATOR_ADDRESS):
        adjudicator.submit_case("CASE-B", CASE_B_FACTS)
        adjudicator.adjudicate("CASE-B")

    calls = emitted("finalized")
    methods = [c["method"] for c in calls]
    assert methods[0] == "create_holding"
    assert "cite_by_case" in methods
    cite = [c for c in calls if c["method"] == "cite_by_case"][0]
    assert cite["args"][1] == first
    assert cite["args"][2] == "FOLLOWS"

    replay(sender=ADJUDICATOR_ADDRESS)
    second = [h["holding_id"] for h in registry.get_holdings() if h["holding_id"] != first][0]
    make_final(registry, second)
    with as_sender(ADJUDICATOR_ADDRESS):
        registry.cite(second, first, "FOLLOWS", "CASE-B")

    citations = registry.get_citations(first)
    assert any(c["relationship"] == "FOLLOWS" and c["source_holding_id"] == second for c in citations)


# ---------------------------------------------------------------------------
# STEP 5-6 · distinguish
# ---------------------------------------------------------------------------
def test_panel_distinguishes_on_a_material_difference(registry, adjudicator):
    stub_llm_response(llm())
    with as_sender(ADJUDICATOR_ADDRESS):
        adjudicator.submit_case("CASE-A", CASE_A_FACTS)
        adjudicator.adjudicate("CASE-A")
    replay(sender=ADJUDICATOR_ADDRESS)
    first = registry.get_holdings()[0]["holding_id"]
    make_final(registry, first)

    stub_llm_response(llm(verdict="REJECTED", used=[first], distinguished=True, reason=GOOD_REASON))
    with as_sender(ADJUDICATOR_ADDRESS):
        adjudicator.submit_case("CASE-C", CASE_C_FACTS)
        adjudicator.adjudicate("CASE-C")

    cite = [c for c in emitted("finalized") if c["method"] == "cite_by_case"][0]
    assert cite["args"][2] == "DISTINGUISHES"
    assert adjudicator.get_case("CASE-C")["distinguishment"] == GOOD_REASON

    replay(sender=ADJUDICATOR_ADDRESS)
    third = [h["holding_id"] for h in registry.get_holdings() if h["holding_id"] != first][0]
    assert registry.get_holding(third)["distinguishment"] == GOOD_REASON
    make_final(registry, third)
    with as_sender(ADJUDICATOR_ADDRESS):
        registry.cite(third, first, "DISTINGUISHES", "CASE-C")

    assert registry.get_holding(first)["distinguishment_count"] == 1
    assert registry.get_distinguishments(first)[0]["holding_id"] == third


@pytest.mark.parametrize(
    "reason",
    [
        "The circumstances differ.",
        "This case is different.",
        "Not applicable here.",
        "Too short.",
    ],
)
def test_generic_distinguishment_is_rejected(registry, adjudicator, reason):
    stub_llm_response(llm())
    with as_sender(ADJUDICATOR_ADDRESS):
        adjudicator.submit_case("CASE-A", CASE_A_FACTS)
        adjudicator.adjudicate("CASE-A")
    replay(sender=ADJUDICATOR_ADDRESS)
    first = registry.get_holdings()[0]["holding_id"]
    make_final(registry, first)

    stub_llm_response(
        llm(verdict="REJECTED", used=[first], distinguished=True, reason=reason)
    )
    with as_sender(ADJUDICATOR_ADDRESS):
        adjudicator.submit_case("CASE-D", CASE_C_FACTS)
        with pytest.raises(genlayer.UserError):
            adjudicator.adjudicate("CASE-D")


# ---------------------------------------------------------------------------
# the prompt
# ---------------------------------------------------------------------------
def test_prompt_contains_retrieved_precedent_and_the_rule(registry, adjudicator):
    stub_llm_response(llm())
    with as_sender(ADJUDICATOR_ADDRESS):
        adjudicator.submit_case("CASE-A", CASE_A_FACTS)
        adjudicator.adjudicate("CASE-A")
    replay(sender=ADJUDICATOR_ADDRESS)
    first = registry.get_holdings()[0]["holding_id"]
    make_final(registry, first)

    stub_llm_response(llm(used=[first]))
    with as_sender(ADJUDICATOR_ADDRESS):
        adjudicator.submit_case("CASE-B", CASE_B_FACTS)
        adjudicator.adjudicate("CASE-B")

    from tests.conftest import gl

    prompt = gl.nondet.prompt_calls[-1]
    assert first in prompt, "retrieved precedent must be in the prompt"
    assert "PRECEDENT RULE" in prompt
    assert "material distinction" in prompt
    assert "REJECTED:" in prompt and "ACCEPTED:" in prompt


def test_prompt_states_cold_start_when_no_precedent(adjudicator):
    stub_llm_response(llm())
    with as_sender(ADJUDICATOR_ADDRESS):
        adjudicator.submit_case("CASE-A", CASE_A_FACTS)
        adjudicator.adjudicate("CASE-A")

    from tests.conftest import gl

    assert "No precedent was retrieved" in gl.nondet.prompt_calls[-1]
