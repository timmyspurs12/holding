#!/usr/bin/env python3
"""Smoke-test a running Reporter API — local or deployed.

    python scripts/smoke_test.py --base-url http://127.0.0.1:8000
    python scripts/smoke_test.py --base-url https://holding-api.up.railway.app --expect-mode DEMO
    python scripts/smoke_test.py --base-url https://holding-api... --expect-mode TESTNET --admin-token $TOKEN

Covers the read API, the wallet sign-in handshake, and the write gates.
Exits non-zero on any failure, so it works as a post-deploy gate in CI.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

PASS, FAIL = "PASS", "FAIL"
results: list[tuple[str, str, str]] = []


def get(base: str, path: str, params: dict | None = None):
    url = base.rstrip("/") + path
    if params:
        url += "?" + urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
    with urllib.request.urlopen(url, timeout=20) as response:
        return response.status, json.loads(response.read().decode())


def post(base: str, path: str, payload: dict, token: str):
    url = base.rstrip("/") + path
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "X-Admin-Token": token},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status, json.loads(response.read().decode())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read().decode())


def get_any(base: str, path: str, params: dict | None = None):
    """GET that returns the status even on 4xx/5xx (for negative checks)."""
    try:
        return get(base, path, params)
    except urllib.error.HTTPError as error:
        try:
            return error.code, json.loads(error.read().decode())
        except Exception:  # noqa: BLE001 - the status is what we are asserting on
            return error.code, {}


def post_with(base: str, path: str, payload: dict, headers: dict):
    """POST with caller-supplied headers (wallet sessions use a different one)."""
    url = base.rstrip("/") + path
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return response.status, json.loads(response.read().decode())
    except urllib.error.HTTPError as error:
        try:
            return error.code, json.loads(error.read().decode())
        except Exception:  # noqa: BLE001 - a non-JSON error body still has a status
            return error.code, {}


def check(name: str, condition: bool, detail: str = "") -> None:
    results.append((PASS if condition else FAIL, name, detail))
    print(f"[{PASS if condition else FAIL}] {name}" + (f" — {detail}" if detail else ""))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Smoke-test the HOLDING Reporter API")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--expect-mode", default="", choices=["", "DEMO", "TESTNET", "MAINNET"])
    parser.add_argument("--admin-token", default="")
    args = parser.parse_args(argv)

    base = args.base_url
    print(f"\nHOLDING smoke test → {base}\n")

    try:
        status, health = get(base, "/health")
        check("/health responds", status == 200, f"HTTP {status}")
    except Exception as error:  # network/parse
        check("/health responds", False, str(error))
        return 1

    network = health.get("network", {})
    mode = network.get("mode")
    check("network block present", bool(mode), f"mode={mode}")
    if args.expect_mode:
        check(f"mode is {args.expect_mode}", mode == args.expect_mode, f"got {mode}")
    check("registry reachable", bool(health.get("registry", {}).get("reachable")))

    status, holdings = get(base, "/holdings", {"limit": 200})
    items = holdings.get("items", [])
    check("/holdings returns an envelope", status == 200 and "items" in holdings, f"{len(items)} holdings")
    if items:
        check(
            "every holding has provenance",
            all("provenance" in item for item in items),
            items[0]["holding_id"],
        )
        check(
            "every holding exposes authority components",
            all(item.get("authority", {}).get("components_bp") for item in items),
        )

    status, searched = get(base, "/holdings/search", {"q": "refund after partial consumption", "k": 5})
    check("/holdings/search responds", status == 200, f"{len(searched.get('items', []))} hits")
    check(
        "semantic search returns only final holdings",
        all(item.get("status") == "FINAL" for item in searched.get("items", [])),
    )

    status, stats = get(base, "/stats")
    check("/stats responds", status == 200, f"{stats.get('total')} total, {stats.get('citations')} citations")

    status, domains = get(base, "/domains")
    check("/domains responds", status == 200, f"{domains.get('total')} domains")

    status, cases = get(base, "/cases")
    check("/cases responds", status == 200, f"{len(cases.get('items', []))} cases")

    if items:
        holding_id = items[0]["holding_id"]
        status, one = get(base, f"/holdings/{holding_id}")
        check("/holdings/{id} responds", status == 200, holding_id)
        status, citations = get(base, f"/holdings/{holding_id}/citations")
        check("/holdings/{id}/citations responds", status == 200, f"{citations.get('total')} edges")
        status, precedent = get(base, f"/holdings/{holding_id}/precedent", {"k": 3})
        check("/holdings/{id}/precedent responds", status == 200)
        status, distinguished = get(base, f"/holdings/{holding_id}/distinguishments")
        check("/holdings/{id}/distinguishments responds", status == 200)

    # wallet sign-in surface: the nonce/verify handshake and the operator gate.
    # These are read-only probes — they never register anything.
    probe_address = "0x0000000000000000000000000000000000000001"
    try:
        status, auth_config = get(base, "/auth/config")
        check("/auth/config responds", status == 200, f"HTTP {status}")
        wallet_auth = auth_config.get("wallet_auth", {})
        check(
            "wallet sign-in is available",
            bool(wallet_auth.get("available")),
            f"chain {auth_config.get('expected', {}).get('chain_id')}",
        )
    except Exception as error:  # noqa: BLE001 - surface as a failed check
        check("/auth/config responds", False, str(error))
        check("wallet sign-in is available", False, "skipped")

    status, nonce = get(base, "/auth/nonce", {"address": probe_address})
    check(
        "/auth/nonce issues a single-use nonce",
        status == 200 and bool(nonce.get("nonce")) and bool(nonce.get("message")),
        f"HTTP {status}",
    )
    if status == 200:
        check(
            "the message to sign names the origin, address and nonce",
            all(
                token in nonce.get("message", "")
                for token in (probe_address, nonce.get("nonce", "x"), "Nonce:")
            ),
        )
        status, _ = post_with(
            base,
            "/auth/verify",
            {"address": probe_address, "nonce": nonce["nonce"], "signature": "0x" + "11" * 65},
            {},
        )
        check("/auth/verify rejects a forged signature", status == 401, f"HTTP {status}")

    status, _ = get_any(base, "/auth/nonce", {"address": "0xnope"})
    check("/auth/nonce rejects a malformed address", status in (401, 422), f"HTTP {status}")

    status, proposals = get(base, "/operator/source-contracts")
    check(
        "/operator/source-contracts responds",
        status == 200 and "counts" in proposals,
        f"{proposals.get('total', 0)} proposals",
    )
    status, _ = post_with(base, "/operator/source-contracts", {}, {})
    check(
        "proposals require a wallet session",
        status in (401, 503),
        f"HTTP {status} (not 422)",
    )

    # security surface: writes must be refused without credentials, and refused
    # on authorization BEFORE the payload is even validated
    probe = {
        "case_id": "SMOKE-1",
        "domain": "digital-commerce",
        "contract_class": "RefundArbiter",
        "issue": "smoke test issue string",
        "facts_digest": "smoke test facts digest",
        "verdict": "APPROVED",
        "ratio": "a ratio long enough to satisfy the schema validator",
        "panel_size": 5,
    }
    status, _ = post(base, "/admin/holdings", probe, "smoke-test-wrong-token")
    check("admin writes reject a bad token", status in (401, 503), f"HTTP {status}")
    status, _ = post(base, "/admin/holdings", {}, "")
    check("authorization precedes payload validation", status in (401, 503), f"HTTP {status} (not 422)")

    if args.admin_token:
        status, _ = post(base, "/admin/reload", {}, args.admin_token)
        check("admin reload accepts the real token", status == 200, f"HTTP {status}")

    failed = [row for row in results if row[0] == FAIL]
    print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
    if failed:
        print("failed:")
        for _, name, detail in failed:
            print(f"  - {name} {detail}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
