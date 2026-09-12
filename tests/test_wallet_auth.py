"""Wallet sign-in and source-contract registration.

The point of these tests is the security boundary, not the plumbing:

  * a signature proves control of an address, once, for one origin;
  * a session can propose but cannot write to the registry;
  * approving is what touches the contract, and it needs the admin token;
  * authorization is checked before the payload is parsed (401, not 422).
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from services.api.main import create_app
from services.api.wallet import build_message, issue_session, normalize_address, session_secret
from services.lib.genlayer.client import get_registry, reset
from services.lib.genlayer.config import GenLayerConfig
from services.lib.genlayer.types import NetworkMode

ALICE_KEY = "0x" + "11" * 32
BOB_KEY = "0x" + "22" * 32

ALICE = "0x1F1cE4ac1F1cE4ac1F1cE4ac1F1cE4ac1F1cE4ac"[:42].lower()
BOB = "0x2B2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b2b"[:42].lower()

ETH = pytest.importorskip("eth_account", reason="eth-account is required for wallet sign-in")
from eth_account import Account  # noqa: E402
from eth_account.messages import encode_defunct  # noqa: E402

ALICE_ADDRESS = Account.from_key(ALICE_KEY).address.lower()
BOB_ADDRESS = Account.from_key(BOB_KEY).address.lower()

ADMIN_TOKEN = "test-admin-token"

PROPOSAL = {
    "contract_address": "0x3333333333333333333333333333333333333333",
    "domain": "digital-commerce",
    "contract_class": "RefundArbiter",
    "label": "Escrow referee",
}


def sign(message: str, key: str) -> str:
    """Signature as a wallet returns it: hex, no 0x prefix."""
    return Account.from_key(key).sign_message(encode_defunct(text=message)).signature.hex()


@pytest.fixture()
def sources_db(tmp_path, monkeypatch):
    path = tmp_path / "sources.json"
    monkeypatch.setenv("HOLDING_SOURCES_DB", str(path))
    return path


@pytest.fixture()
def app(sources_db):
    # The registry client is cached per config, and the DEMO chain holds state
    # (registered sources, seeded holdings) in memory. Reset it so one test
    # cannot see another test's registrations.
    reset()
    config = GenLayerConfig(
        mode=NetworkMode.DEMO,
        admin_token=ADMIN_TOKEN,
        operator_addresses=(ALICE_ADDRESS,),
    )
    application = create_app(config)
    application.state.sources.path = sources_db
    return application


@pytest.fixture()
def client(app):
    with TestClient(app) as test_client:
        yield test_client


def sign_in(client, address, key):
    nonce_payload = client.get("/auth/nonce", params={"address": address}).json()
    signature = sign(nonce_payload["message"], key)
    response = client.post(
        "/auth/verify",
        json={"address": address, "nonce": nonce_payload["nonce"], "signature": signature},
    )
    return nonce_payload, response


# -- pure helpers --------------------------------------------------------


def test_normalize_address_accepts_and_lowercases():
    assert normalize_address("0xAbC0000000000000000000000000000000000001") == (
        "0xabc0000000000000000000000000000000000001"
    )


@pytest.mark.parametrize("bad", ["", "0x123", "0xZZ" + "0" * 38, "not-an-address"])
def test_normalize_address_rejects(bad):
    with pytest.raises(ValueError):
        normalize_address(bad)


def test_message_is_deterministic_and_complete():
    first = build_message(uri="https://holding.test", address=ALICE_ADDRESS, nonce="abc", issued_at=1_700_000_000, chain_id=4221)
    second = build_message(uri="https://holding.test", address=ALICE_ADDRESS, nonce="abc", issued_at=1_700_000_000, chain_id=4221)
    assert first == second
    for token in ("https://holding.test", ALICE_ADDRESS, "Chain ID: 4221", "Nonce: abc"):
        assert token in first


def test_session_secret_derives_from_admin_token():
    with_token = GenLayerConfig(mode=NetworkMode.DEMO, admin_token="abc")
    without = GenLayerConfig(mode=NetworkMode.DEMO)
    assert session_secret(with_token)
    assert session_secret(without) == ""
    assert session_secret(with_token) == session_secret(GenLayerConfig(mode=NetworkMode.DEMO, admin_token="abc"))
    assert session_secret(with_token) != session_secret(GenLayerConfig(mode=NetworkMode.DEMO, admin_token="abd"))


# -- the sign-in handshake ----------------------------------------------


def test_auth_config_reports_state(client):
    payload = client.get("/auth/config").json()
    assert payload["wallet_auth"]["available"] is True
    assert payload["expected"]["mode"] == "DEMO"
    assert payload["operator_allowlist"]["count"] == 1


def test_happy_path_returns_a_session(client):
    nonce_payload, response = sign_in(client, ALICE_ADDRESS, ALICE_KEY)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["token_type"] == "Bearer"
    assert body["session"]["address"] == ALICE_ADDRESS
    assert body["session"]["is_operator"] is True
    assert body["network"]["mode"] == "DEMO"


def test_non_operator_is_labelled(client):
    _, response = sign_in(client, BOB_ADDRESS, BOB_KEY)
    assert response.status_code == 200
    assert response.json()["session"]["is_operator"] is False


def test_wrong_signer_is_rejected(client):
    nonce_payload = client.get("/auth/nonce", params={"address": ALICE_ADDRESS}).json()
    # Bob signs Alice's nonce.
    signature = sign(nonce_payload["message"], BOB_KEY)
    response = client.post(
        "/auth/verify",
        json={"address": ALICE_ADDRESS, "nonce": nonce_payload["nonce"], "signature": signature},
    )
    assert response.status_code == 401


def test_nonce_is_single_use(client):
    nonce_payload, first = sign_in(client, ALICE_ADDRESS, ALICE_KEY)
    assert first.status_code == 200
    again = client.post(
        "/auth/verify",
        json={
            "address": ALICE_ADDRESS,
            "nonce": nonce_payload["nonce"],
            "signature": sign(nonce_payload["message"], ALICE_KEY),
        },
    )
    assert again.status_code == 401


def test_expired_nonce_is_rejected(client, app):
    nonce_payload = client.get("/auth/nonce", params={"address": ALICE_ADDRESS}).json()
    app.state.nonces.ttl = -1
    response = client.post(
        "/auth/verify",
        json={
            "address": ALICE_ADDRESS,
            "nonce": nonce_payload["nonce"],
            "signature": sign(nonce_payload["message"], ALICE_KEY),
        },
    )
    assert response.status_code == 401


def test_signature_bound_to_origin(app, sources_db):
    """A signature made for one origin must not work on another."""
    other = GenLayerConfig(
        mode=NetworkMode.DEMO,
        admin_token=ADMIN_TOKEN,
        public_origin="https://somewhere.else",
    )
    with TestClient(create_app(other)) as other_client:
        nonce_payload = other_client.get("/auth/nonce", params={"address": ALICE_ADDRESS}).json()

    with TestClient(app) as client:
        response = client.post(
            "/auth/verify",
            json={
                "address": ALICE_ADDRESS,
                "nonce": nonce_payload["nonce"],
                "signature": sign(nonce_payload["message"], ALICE_KEY),
            },
        )
    assert response.status_code == 401


def test_client_supplied_message_is_ignored(client):
    """The server rebuilds the text; sending a different one must not help."""
    nonce_payload = client.get("/auth/nonce", params={"address": ALICE_ADDRESS}).json()
    forged = build_message(
        uri="https://evil.test",
        address=ALICE_ADDRESS,
        nonce=nonce_payload["nonce"],
        issued_at=nonce_payload["issued_at"],
        chain_id=0,
    )
    response = client.post(
        "/auth/verify",
        json={
            "address": ALICE_ADDRESS,
            "nonce": nonce_payload["nonce"],
            "signature": sign(forged, ALICE_KEY),
            "message": forged,
        },
    )
    assert response.status_code == 401


def test_bad_address_on_nonce(client):
    assert client.get("/auth/nonce", params={"address": "0xdeadbeef"}).status_code == 422


# -- session use ---------------------------------------------------------


def test_session_is_accepted_by_operator_routes(client):
    _, response = sign_in(client, ALICE_ADDRESS, ALICE_KEY)
    token = response.json()["token"]
    me = client.get("/operator/me", headers={"X-Session-Token": token})
    assert me.status_code == 200
    assert me.json()["session"]["address"] == ALICE_ADDRESS


def test_session_also_works_as_bearer(client):
    _, response = sign_in(client, ALICE_ADDRESS, ALICE_KEY)
    token = response.json()["token"]
    me = client.get("/operator/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200


def test_forged_session_is_rejected(client):
    _, response = sign_in(client, ALICE_ADDRESS, ALICE_KEY)
    token = response.json()["token"]
    forged = token[:-1] + ("0" if token[-1] != "0" else "1")
    assert client.get("/operator/me", headers={"X-Session-Token": forged}).status_code == 401


def test_session_swapping_address_is_rejected(client, app):
    config = app.state.config
    secret = session_secret(config)
    token, _ = issue_session(secret, BOB_ADDRESS)
    assert client.get("/operator/me", headers={"X-Session-Token": token}).status_code == 200
    swapped = token.replace(BOB_ADDRESS, ALICE_ADDRESS)
    assert client.get("/operator/me", headers={"X-Session-Token": swapped}).status_code == 401


def test_expired_session_is_rejected(client, app):
    secret = session_secret(app.state.config)
    token, _ = issue_session(secret, ALICE_ADDRESS, now=time.time() - 10_000, ttl=1)
    assert client.get("/operator/me", headers={"X-Session-Token": token}).status_code == 401


def test_sign_in_disabled_without_a_secret(sources_db):
    config = GenLayerConfig(mode=NetworkMode.DEMO)  # no admin token, no session secret
    with TestClient(create_app(config)) as client:
        assert client.get("/auth/config").json()["wallet_auth"]["available"] is False
        assert client.get("/auth/nonce", params={"address": ALICE_ADDRESS}).status_code == 200
        assert client.post("/auth/verify", json={"address": ALICE_ADDRESS, "nonce": "x", "signature": "0x0"}).status_code == 503


# -- proposals -----------------------------------------------------------


def test_anonymous_proposal_is_unauthorized_not_unprocessable(client):
    """Authorization must be decided before the payload is parsed."""
    response = client.post("/operator/source-contracts", json={})
    assert response.status_code == 401, response.text


def test_proposal_is_pending_and_touches_nothing(client, app):
    before = client.get("/stats").json()["total"]
    _, auth = sign_in(client, ALICE_ADDRESS, ALICE_KEY)
    token = auth.json()["token"]

    response = client.post(
        "/operator/source-contracts",
        json=PROPOSAL,
        headers={"X-Session-Token": token},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["status"] == "PENDING"
    assert body["submitted_by"] == ALICE_ADDRESS

    registry = client.get("/stats").json()
    assert registry["total"] == before, "a proposal must not create a holding"

    contract = get_registry(app.state.config)
    assert contract.is_registered_source(PROPOSAL["contract_address"]) is False


def test_duplicate_proposal_conflicts(client):
    _, auth = sign_in(client, ALICE_ADDRESS, ALICE_KEY)
    token = auth.json()["token"]
    first = client.post("/operator/source-contracts", json=PROPOSAL, headers={"X-Session-Token": token})
    assert first.status_code == 201
    second = client.post("/operator/source-contracts", json=PROPOSAL, headers={"X-Session-Token": token})
    assert second.status_code == 409


@pytest.mark.parametrize(
    "field,value",
    [
        ("contract_address", "0xnope"),
        ("domain", "Not A Slug"),
        ("contract_class", "!!!"),
        ("deploy_tx", "0x1234"),
    ],
)
def test_malformed_proposal_is_rejected(client, field, value):
    _, auth = sign_in(client, ALICE_ADDRESS, ALICE_KEY)
    token = auth.json()["token"]
    payload = {**PROPOSAL, field: value}
    response = client.post("/operator/source-contracts", json=payload, headers={"X-Session-Token": token})
    assert response.status_code == 422


def test_demo_placeholder_address_is_rejected(client):
    _, auth = sign_in(client, ALICE_ADDRESS, ALICE_KEY)
    token = auth.json()["token"]
    response = client.post(
        "/operator/source-contracts",
        json={**PROPOSAL, "contract_address": "0xDEMO000000000000000000000000000000000001"},
        headers={"X-Session-Token": token},
    )
    assert response.status_code == 422


def test_proposal_list_is_public(client):
    _, auth = sign_in(client, ALICE_ADDRESS, ALICE_KEY)
    client.post("/operator/source-contracts", json=PROPOSAL, headers={"X-Session-Token": auth.json()["token"]})
    listing = client.get("/operator/source-contracts").json()
    assert listing["total"] == 1
    assert listing["counts"]["PENDING"] == 1
    assert listing["items"][0]["contract_address"] == PROPOSAL["contract_address"]


# -- approval (the step that reaches the contract) ----------------------


def test_approval_requires_the_admin_token(client):
    _, auth = sign_in(client, ALICE_ADDRESS, ALICE_KEY)
    token = auth.json()["token"]
    created = client.post("/operator/source-contracts", json=PROPOSAL, headers={"X-Session-Token": token}).json()

    # A wallet session is not enough, and the answer is 401 rather than 422.
    refused = client.post(
        f"/admin/source-contracts/{created['proposal_id']}/approve",
        json={"note": "let me in"},
        headers={"X-Session-Token": token},
    )
    assert refused.status_code == 401

    approved = client.post(
        f"/admin/source-contracts/{created['proposal_id']}/approve",
        json={"note": "verified deploy tx"},
        headers={"X-Admin-Token": ADMIN_TOKEN, "Idempotency-Key": "approve-1"},
    )
    assert approved.status_code == 200, approved.text
    body = approved.json()
    assert body["status"] == "APPROVED"
    assert body["registered_on_chain"] is True

    contract = get_registry(client.app.state.config)
    assert contract.is_registered_source(PROPOSAL["contract_address"]) is True


def test_rejection_never_registers(client):
    _, auth = sign_in(client, ALICE_ADDRESS, ALICE_KEY)
    token = auth.json()["token"]
    created = client.post("/operator/source-contracts", json=PROPOSAL, headers={"X-Session-Token": token}).json()

    rejected = client.post(
        f"/admin/source-contracts/{created['proposal_id']}/reject",
        json={"note": "not an adjudicator"},
        headers={"X-Admin-Token": ADMIN_TOKEN, "Idempotency-Key": "reject-1"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "REJECTED"
    assert rejected.json()["registered_on_chain"] is False

    contract = get_registry(client.app.state.config)
    assert contract.is_registered_source(PROPOSAL["contract_address"]) is False


def test_unknown_proposal_is_a_404(client):
    response = client.post(
        "/admin/source-contracts/SRC-NOPE/approve",
        json={},
        headers={"X-Admin-Token": ADMIN_TOKEN, "Idempotency-Key": "k"},
    )
    assert response.status_code == 404


def test_double_decision_conflicts(client):
    _, auth = sign_in(client, ALICE_ADDRESS, ALICE_KEY)
    token = auth.json()["token"]
    created = client.post("/operator/source-contracts", json=PROPOSAL, headers={"X-Session-Token": token}).json()

    first = client.post(
        f"/admin/source-contracts/{created['proposal_id']}/approve",
        json={},
        headers={"X-Admin-Token": ADMIN_TOKEN, "Idempotency-Key": "a"},
    )
    assert first.status_code == 200
    second = client.post(
        f"/admin/source-contracts/{created['proposal_id']}/approve",
        json={},
        headers={"X-Admin-Token": ADMIN_TOKEN, "Idempotency-Key": "b"},
    )
    assert second.status_code == 409


def test_admin_decision_is_replayed_not_repeated(client):
    _, auth = sign_in(client, ALICE_ADDRESS, ALICE_KEY)
    token = auth.json()["token"]
    created = client.post("/operator/source-contracts", json=PROPOSAL, headers={"X-Session-Token": token}).json()
    headers = {"X-Admin-Token": ADMIN_TOKEN, "Idempotency-Key": "same-key"}
    path = f"/admin/source-contracts/{created['proposal_id']}/approve"

    first = client.post(path, json={}, headers=headers).json()
    second = client.post(path, json={}, headers=headers).json()
    assert second["replayed"] is True
    assert second["transaction_reference"] == first["transaction_reference"]
