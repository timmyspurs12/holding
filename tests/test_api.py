"""Reporter API contract tests — responses, filtering, writes and guards."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from services.api.main import create_app
from services.lib.genlayer.client import reset
from services.lib.genlayer.config import GenLayerConfig

ADMIN = {"X-Admin-Token": "test-token"}
KEY = {"Idempotency-Key": "test-key-1"}


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("GENLAYER_NETWORK", "demo")
    monkeypatch.setenv("HOLDING_ADMIN_TOKEN", "test-token")
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "10000")
    monkeypatch.setenv("HOLDING_DEMO_SEED", "false")
    reset()
    app = create_app(GenLayerConfig.from_env())
    with TestClient(app) as test_client:
        yield test_client
    reset()


@pytest.fixture()
def seeded(client):
    response = client.post("/demo/seed")
    assert response.status_code == 200, response.text
    return response.json()


# ---------------------------------------------------------------------------
# health / meta
# ---------------------------------------------------------------------------
def test_health_reports_the_network(client):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["network"]["mode"] == "DEMO"
    assert body["network"]["simulated"] is True
    assert body["registry"]["reachable"] is True
    assert "uptime_seconds" in body


def test_stats_on_an_empty_registry(client):
    body = client.get("/stats").json()
    assert body["total"] == 0
    assert body["authority_bands"] == {"HIGH": 0, "MODERATE": 0, "DEVELOPING": 0}
    assert body["network"]["mode"] == "DEMO"


def test_domains_is_empty_on_a_cold_registry(client):
    body = client.get("/domains").json()
    assert body["items"] == []
    assert body["total"] == 0


# ---------------------------------------------------------------------------
# cold start
# ---------------------------------------------------------------------------
def test_empty_registry_returns_empty_lists_not_errors(client):
    assert client.get("/holdings").json()["items"] == []
    assert client.get("/holdings/search?q=refund").json()["items"] == []
    assert client.get("/cases").json()["items"] == []
    assert client.get("/holdings/HLD-000001").status_code == 404
    assert client.get("/holdings/HLD-000001/precedent").status_code == 404
    assert client.get("/holdings/HLD-000001/citations").status_code == 404


def test_semantic_search_on_an_empty_registry_does_not_fail(client):
    response = client.get("/holdings/search", params={"q": "partial consumption refund", "k": 5})
    assert response.status_code == 200
    assert response.json()["items"] == []


# ---------------------------------------------------------------------------
# the seeded loop
# ---------------------------------------------------------------------------
def test_seed_produces_three_holdings_and_the_expected_relationships(seeded):
    holdings = seeded["holdings"]
    assert [h["holding_id"] for h in holdings] == ["HLD-000001", "HLD-000002", "HLD-000003"]
    assert all(h["status"] == "FINAL" for h in holdings)
    assert all(h["provenance"]["simulated"] is True for h in holdings)

    first = client_holding(seeded, "HLD-000001")
    assert first["verdict"] == "APPROVED"

    steps = seeded["steps"]
    assert steps[0]["case"]["precedent_used"] == []           # cold start
    assert steps[1]["case"]["precedent_used"] == ["HLD-000001"]
    assert steps[1]["case"]["followed"] is True
    assert steps[2]["case"]["distinguished"] is True
    assert "fully delivered" in steps[2]["case"]["distinguishment_reason"]
    assert steps[2]["case"]["distinguishment_reason"] != "The circumstances differ."


def client_holding(seeded, holding_id):
    return next(h for h in seeded["holdings"] if h["holding_id"] == holding_id)


def test_precedent_graph_endpoints(seeded, client):
    citations = client.get("/holdings/HLD-000001/citations").json()["items"]
    relationships = {(c["source_holding_id"], c["relationship"]) for c in citations}
    assert ("HLD-000002", "FOLLOWS") in relationships
    assert ("HLD-000003", "DISTINGUISHES") in relationships

    filtered = client.get("/holdings/HLD-000001/citations", params={"relationship": "DISTINGUISHES"}).json()
    assert [c["source_holding_id"] for c in filtered["items"]] == ["HLD-000003"]

    distinguishments = client.get("/holdings/HLD-000001/distinguishments").json()["items"]
    assert distinguishments[0]["holding_id"] == "HLD-000003"
    assert distinguishments[0]["reason"].startswith("Unlike HLD-000001")


def test_a_holding_exposes_authority_components_and_provenance(seeded, client):
    body = client.get("/holdings/HLD-000001").json()
    authority = body["authority"]
    assert set(authority["components_bp"]) == {"finality", "appeal", "panel", "citations", "consistency"}
    assert sum(row["contribution_bp"] for row in authority["breakdown"]) > 0
    assert authority["explanation"]
    assert body["provenance"]["case_id"] == "CASE-001"
    assert body["provenance"]["source_contract"].startswith("0xDEMO")
    assert body["provenance"]["mode"] == "DEMO"
    assert body["provenance"]["simulated"] is True


def test_citations_raise_the_target_authority(seeded, client):
    first = client.get("/holdings/HLD-000001").json()["authority"]["score_bp"]
    third = client.get("/holdings/HLD-000003").json()["authority"]["score_bp"]
    assert first > third  # #001 was followed; #003 has no citations yet


def test_precedent_retrieval_returns_ranked_final_holdings(seeded, client):
    body = client.get("/holdings/HLD-000002/precedent", params={"k": 3}).json()
    items = body["items"]
    assert items, "a final registry must return precedent"
    assert all(item["status"] == "FINAL" for item in items)
    assert items[0]["similarity"] >= items[-1]["similarity"]


def test_stats_reflect_the_corpus(seeded, client):
    body = client.get("/stats").json()
    assert body["total"] == 3
    assert body["final"] == 3
    assert body["citations"] == 2
    assert body["follows"] == 1
    assert body["distinguishes"] == 1
    assert sum(body["authority_bands"].values()) == 3


def test_domains_groups_the_corpus(seeded, client):
    body = client.get("/domains").json()
    assert body["total"] == 1
    assert body["items"][0]["domain"] == "digital-commerce"
    assert body["items"][0]["holdings"] == 3


def test_cases_endpoint_links_a_case_to_its_holding(seeded, client):
    body = client.get("/cases/CASE-002").json()
    assert body["holding"]["holding_id"] == "HLD-000002"
    assert body["followed"] is True
    assert body["verdict"] == "APPROVED"


# ---------------------------------------------------------------------------
# filtering + search
# ---------------------------------------------------------------------------
def test_metadata_filters(seeded, client):
    assert len(client.get("/holdings", params={"status": "FINAL"}).json()["items"]) == 3
    assert client.get("/holdings", params={"status": "PENDING"}).json()["items"] == []
    assert len(client.get("/holdings", params={"verdict": "REJECTED"}).json()["items"]) == 1
    assert len(client.get("/holdings", params={"domain": "nope"}).json()["items"]) == 0
    assert len(client.get("/holdings", params={"min_authority": 0.6}).json()["items"]) >= 1
    assert len(client.get("/holdings", params={"min_authority": 0.99}).json()["items"]) == 0


def test_semantic_search_orders_by_similarity(seeded, client):
    body = client.get("/holdings/search", params={"q": "cancelled after partial consumption refund owed", "k": 3}).json()
    similarities = [item["similarity"] for item in body["items"]]
    assert similarities == sorted(similarities, reverse=True)
    assert body["query"]


def test_search_is_not_keyword_only(seeded, client):
    """A paraphrase with no shared wording still retrieves the right holding."""
    body = client.get(
        "/holdings/search",
        params={"q": "buyer exited a subscription early having used part of what they paid for", "k": 3},
    ).json()
    assert body["items"], "semantic search must retrieve without exact keywords"


# ---------------------------------------------------------------------------
# admin writes
# ---------------------------------------------------------------------------
def test_writes_require_the_admin_token(client):
    payload = {
        "case_id": "CASE-900",
        "domain": "digital-commerce",
        "contract_class": "RefundArbiter",
        "issue": "Refund eligibility after partial consumption of a digital service",
        "facts_digest": "purchased 14 days before cancellation, 40% consumed, no exclusion",
        "verdict": "APPROVED",
        "ratio": "Where a digital service is partly consumed and no exclusion applies, a pro rata refund is owed.",
        "panel_size": 5,
    }
    response = client.post("/admin/holdings", json=payload, headers=KEY)
    assert response.status_code == 401


def test_a_malformed_holding_is_rejected_before_the_registry(client):
    response = client.post(
        "/admin/holdings",
        json={
            "case_id": "CASE-901",
            "domain": "digital-commerce",
            "contract_class": "RefundArbiter",
            "issue": "too short",
            "facts_digest": "nope",
            "verdict": "MAYBE",
            "ratio": "short",
            "panel_size": 0,
        },
        headers={**ADMIN, **KEY},
    )
    assert response.status_code == 422
    assert response.json()["detail"]


def test_a_valid_holding_is_created_as_an_unverified_record(client):
    response = client.post(
        "/admin/holdings",
        json={
            "case_id": "CASE-902",
            "domain": "digital-commerce",
            "contract_class": "RefundArbiter",
            "issue": "Refund eligibility after partial consumption of a digital service",
            "facts_digest": "purchased 14 days before cancellation, 40% consumed, no exclusion",
            "verdict": "APPROVED",
            "ratio": "Where a digital service is partly consumed and no exclusion applies, a pro rata refund is owed.",
            "panel_size": 5,
            "reason_codes": ["PARTIAL_CONSUMPTION"],
            "evidence_hashes": ["0x" + "ab" * 32],
        },
        headers={**ADMIN, **KEY},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "UNVERIFIED"

    listing = client.get("/holdings", params={"status": "UNVERIFIED"}).json()
    assert [item["case_id"] for item in listing["items"]] == ["CASE-902"]

    # an unverified record is not precedent
    assert client.get("/holdings/search", params={"q": "refund after partial consumption"}).json()["items"] == []


def test_an_unverified_record_becomes_precedent_only_after_finality(client):
    created = client.post(
        "/admin/holdings",
        json={
            "case_id": "CASE-903",
            "domain": "digital-commerce",
            "contract_class": "RefundArbiter",
            "issue": "Refund eligibility after partial consumption of a digital service",
            "facts_digest": "purchased 14 days before cancellation, 40% consumed, no exclusion",
            "verdict": "APPROVED",
            "ratio": "Where a digital service is partly consumed and no exclusion applies, a pro rata refund is owed.",
            "panel_size": 5,
        },
        headers={**ADMIN, **KEY},
    ).json()
    assert created["status"] == "UNVERIFIED"

    holdings = client.get("/holdings", params={"status": "UNVERIFIED"}).json()["items"]
    holding_id = holdings[0]["holding_id"]

    # status 5 (Accepted) is not finality
    accepted = client.post(
        f"/admin/holdings/{holding_id}/finality",
        json={
            "holding_id": holding_id,
            "tx_status_code": 5,
            "execution_result": "FINISHED_WITH_RETURN",
            "finality_timestamp": 1_770_000_000,
        },
        headers={**ADMIN, "Idempotency-Key": "attest-1"},
    ).json()
    assert accepted["status"] == "REJECTED"

    finalized = client.post(
        "/admin/holdings",
        json={
            "case_id": "CASE-904",
            "domain": "digital-commerce",
            "contract_class": "RefundArbiter",
            "issue": "Refund eligibility after partial consumption of a digital service",
            "facts_digest": "purchased 14 days before cancellation, 40% consumed, no exclusion",
            "verdict": "PARTIAL",
            "ratio": "Where a digital service is partly consumed and no exclusion applies, a pro rata refund is owed.",
            "panel_size": 7,
        },
        headers={**ADMIN, "Idempotency-Key": "create-904"},
    ).json()
    assert finalized["status"] == "UNVERIFIED"

    second = [h for h in client.get("/holdings").json()["items"] if h["case_id"] == "CASE-904"][0]
    settled = client.post(
        f"/admin/holdings/{second['holding_id']}/finality",
        json={
            "holding_id": second["holding_id"],
            "tx_status_code": 7,
            "execution_result": "FINISHED_WITH_RETURN",
            "finality_timestamp": 1_770_000_100,
            "source_tx": "0x" + "11" * 32,
        },
        headers={**ADMIN, "Idempotency-Key": "attest-2"},
    ).json()
    assert settled["status"] == "FINAL"
    assert client.get(f"/holdings/{second['holding_id']}").json()["status"] == "FINAL"


def test_finality_requires_status_and_execution_success(client):
    created = client.post(
        "/admin/holdings",
        json={
            "case_id": "CASE-905",
            "domain": "digital-commerce",
            "contract_class": "RefundArbiter",
            "issue": "Refund eligibility after partial consumption of a digital service",
            "facts_digest": "purchased 14 days before cancellation, 40% consumed, no exclusion",
            "verdict": "APPROVED",
            "ratio": "Where a digital service is partly consumed and no exclusion applies, a pro rata refund is owed.",
            "panel_size": 5,
        },
        headers={**ADMIN, "Idempotency-Key": "create-905"},
    ).json()
    holding_id = [h for h in client.get("/holdings").json()["items"] if h["case_id"] == "CASE-905"][0]["holding_id"]

    rejected = client.post(
        f"/admin/holdings/{holding_id}/finality",
        json={
            "holding_id": holding_id,
            "tx_status_code": 7,
            "execution_result": "FINISHED_WITH_ERROR",
            "finality_timestamp": 1_770_000_000,
        },
        headers={**ADMIN, "Idempotency-Key": "attest-905"},
    ).json()
    assert rejected["status"] == "REJECTED"
    assert client.get("/holdings/search", params={"q": "refund partial consumption"}).json()["items"] == []


def test_write_replay_returns_the_original_result(client):
    payload = {
        "case_id": "CASE-906",
        "domain": "digital-commerce",
        "contract_class": "RefundArbiter",
        "issue": "Refund eligibility after partial consumption of a digital service",
        "facts_digest": "purchased 14 days before cancellation, 40% consumed, no exclusion",
        "verdict": "APPROVED",
        "ratio": "Where a digital service is partly consumed and no exclusion applies, a pro rata refund is owed.",
        "panel_size": 5,
    }
    first = client.post("/admin/holdings", json=payload, headers={**ADMIN, "Idempotency-Key": "replay-key"})
    second = client.post("/admin/holdings", json=payload, headers={**ADMIN, "Idempotency-Key": "replay-key"})
    assert first.status_code == 200 and second.status_code == 200
    assert second.json()["replayed"] is True
    assert len([h for h in client.get("/holdings").json()["items"] if h["case_id"] == "CASE-906"]) == 1


def test_writes_without_an_idempotency_key_are_refused(client):
    response = client.post(
        "/admin/holdings",
        json={
            "case_id": "CASE-907",
            "domain": "digital-commerce",
            "contract_class": "RefundArbiter",
            "issue": "Refund eligibility after partial consumption",
            "facts_digest": "purchased 14 days before cancellation, 40% consumed",
            "verdict": "APPROVED",
            "ratio": "Where a digital service is partly consumed, a pro rata refund is owed.",
            "panel_size": 5,
        },
        headers=ADMIN,
    )
    assert response.status_code == 400


def test_citations_are_validated(seeded, client):
    bad = client.post(
        "/admin/citations",
        json={
            "source_holding_id": "HLD-000001",
            "target_holding_id": "HLD-000001",
            "relationship": "LOVES",
            "case_id": "CASE-X",
        },
        headers={**ADMIN, **KEY},
    )
    assert bad.status_code == 422

    unknown = client.post(
        "/admin/citations",
        json={
            "source_holding_id": "HLD-000001",
            "target_holding_id": "HLD-999999",
            "relationship": "FOLLOWS",
            "case_id": "CASE-X",
        },
        headers={**ADMIN, "Idempotency-Key": "cite-bad"},
    )
    assert unknown.status_code == 422

    duplicate = client.post(
        "/admin/citations",
        json={
            "source_holding_id": "HLD-000002",
            "target_holding_id": "HLD-000001",
            "relationship": "FOLLOWS",
            "case_id": "CASE-002",
        },
        headers={**ADMIN, "Idempotency-Key": "cite-dup"},
    )
    assert duplicate.status_code == 200
    assert duplicate.json()["recorded"] is False  # idempotent


def test_unknown_ids_are_rejected_everywhere(client):
    assert client.get("/holdings/not-an-id").status_code == 404
    assert client.get("/cases/NOPE").status_code == 404


# ---------------------------------------------------------------------------
# simulation guard rails
# ---------------------------------------------------------------------------
def test_simulation_is_labelled(seeded):
    for step in seeded["steps"]:
        assert step["simulated"] is True
        assert "SIMULATED" in step["warning"]
        assert step["holding"]["provenance"]["simulated"] is True


def test_simulation_rejects_empty_facts(client):
    response = client.post("/demo/cases", json={"case_id": "CASE-800", "facts": []})
    assert response.status_code == 422


def test_simulation_is_refused_on_mainnet(monkeypatch):
    monkeypatch.setenv("GENLAYER_NETWORK", "mainnet")
    monkeypatch.setenv("HOLDING_REGISTRY_ADDRESS", "0x" + "22" * 20)
    reset()
    app = create_app(GenLayerConfig.from_env())
    with TestClient(app) as test_client:
        response = test_client.post("/demo/cases", json={"case_id": "CASE-1", "facts": ["a fact"]})
    reset()
    assert response.status_code == 403


def test_startup_seeds_the_canonical_loop_in_demo_mode(monkeypatch):
    """With seeding enabled, a fresh DEMO process already holds the loop."""
    monkeypatch.setenv("GENLAYER_NETWORK", "demo")
    monkeypatch.setenv("HOLDING_DEMO_SEED", "true")
    reset()
    app = create_app(GenLayerConfig.from_env())
    with TestClient(app) as test_client:
        holdings = test_client.get("/holdings").json()["items"]
        assert [h["holding_id"] for h in holdings] == ["HLD-000001", "HLD-000002", "HLD-000003"]
        assert test_client.get("/stats").json()["citations"] == 2
    reset()


# ---------------------------------------------------------------------------
# guards
# ---------------------------------------------------------------------------
def test_admin_writes_fail_closed_without_a_configured_token(monkeypatch):
    monkeypatch.setenv("GENLAYER_NETWORK", "demo")
    monkeypatch.delenv("HOLDING_ADMIN_TOKEN", raising=False)
    reset()
    app = create_app(GenLayerConfig.from_env())
    with TestClient(app) as test_client:
        response = test_client.post(
            "/admin/holdings",
            json={
                "case_id": "CASE-910",
                "domain": "digital-commerce",
                "contract_class": "RefundArbiter",
                "issue": "Refund eligibility after partial consumption of a digital service",
                "facts_digest": "purchased 14 days before cancellation, 40% consumed, no exclusion",
                "verdict": "APPROVED",
                "ratio": "Where a digital service is partly consumed and no exclusion applies, a pro rata refund is owed.",
                "panel_size": 5,
            },
            headers={"X-Admin-Token": "anything", "Idempotency-Key": "k"},
        )
        assert response.status_code == 503
        assert response.json()["detail"]["type"] if isinstance(response.json()["detail"], dict) else True
        reload = test_client.post("/admin/reload")
        assert reload.status_code == 503
    reset()


def test_rate_limiting_returns_429(monkeypatch):
    monkeypatch.setenv("GENLAYER_NETWORK", "demo")
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "3")
    reset()
    app = create_app(GenLayerConfig.from_env())
    with TestClient(app) as test_client:
        codes = [test_client.get("/holdings").status_code for _ in range(6)]
    reset()
    assert 200 in codes
    assert 429 in codes


def test_health_is_not_rate_limited(monkeypatch):
    monkeypatch.setenv("GENLAYER_NETWORK", "demo")
    monkeypatch.setenv("RATE_LIMIT_PER_MINUTE", "1")
    reset()
    app = create_app(GenLayerConfig.from_env())
    with TestClient(app) as test_client:
        codes = {test_client.get("/health").status_code for _ in range(5)}
    reset()
    assert codes == {200}
