#!/usr/bin/env python3
"""HOLDING — the six-step loop, run against the contract.

    CASE -> ADJUDICATION -> FINALITY -> HOLDING -> INDEX ->
    PRECEDENT RETRIEVAL -> NEW ADJUDICATION -> FOLLOW / DISTINGUISH -> NEW HOLDING

Expected output in DEMO mode:

    HOLDING #001   cold start            -> APPROVED
    HOLDING #002   FOLLOWS #001          -> APPROVED
    HOLDING #003   DISTINGUISHES #001    -> REJECTED

Usage
-----
    python scripts/demo_loop.py                 # DEMO mode (default)
    GENLAYER_NETWORK=bradbury HOLDING_REGISTRY_ADDRESS=0x... python scripts/demo_loop.py

The script never prints a simulated record as a live one: every line is
prefixed with the network mode it came from.
"""

from __future__ import annotations

import argparse
import os
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.lib.genlayer.base import AdapterError  # noqa: E402
from services.lib.genlayer.client import get_chain, get_registry  # noqa: E402
from services.lib.genlayer.config import GenLayerConfig  # noqa: E402

CASES = [
    (
        "CASE-001",
        [
            "Digital service purchased 14 days before cancellation",
            "Approximately 40% of the entitlement consumed",
            "No usage-based exclusion in the purchase terms",
        ],
    ),
    (
        "CASE-002",
        [
            "Monthly recurring plan, cancelled 14 days into the billing cycle",
            "Approximately 40% of the cycle entitlement consumed",
            "No usage-based exclusion in the plan terms",
        ],
    ),
    (
        "CASE-003",
        [
            "Digital service purchased 12 days before cancellation",
            "The service was fully delivered before cancellation",
            "No usage-based exclusion in the purchase terms",
        ],
    ),
]

WIDTH = 78


def rule(char: str = "-") -> str:
    return char * WIDTH


def heading(text: str) -> None:
    print()
    print(rule("="))
    print(text)
    print(rule("="))


def wrap(text: str, indent: str = "    ") -> str:
    return textwrap.fill(text, width=WIDTH, initial_indent=indent, subsequent_indent=indent)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the HOLDING precedent loop")
    parser.add_argument("--network", default=os.getenv("GENLAYER_NETWORK", "demo"))
    parser.add_argument("--registry", default=os.getenv("HOLDING_REGISTRY_ADDRESS", ""))
    parser.add_argument("--no-settle", action="store_true", help="stop at acceptance (no finality)")
    args = parser.parse_args(argv)

    if args.network != "demo":
        os.environ["GENLAYER_NETWORK"] = args.network
    if args.registry:
        os.environ["HOLDING_REGISTRY_ADDRESS"] = args.registry

    config = GenLayerConfig.from_env()
    registry = get_registry(config)
    chain = get_chain(config)

    heading(f"HOLDING · precedent loop · {config.mode.value} / {config.network}")
    info = config.info()
    print(wrap(info.note))
    print(f"    registry     {config.registry_address}")
    print(f"    adjudicator  {config.adjudicator_address}")

    for index, (case_id, facts) in enumerate(CASES, start=1):
        heading(f"STEP {index * 2 - 1} · CASE {case_id} submitted for adjudication")
        for fact in facts:
            print(f"    - {fact}")

        submitted = registry.submit_case(case_id, facts, sender=registry.adjudicator_address)
        print(f"\n    submitted      {submitted.transaction_reference}  ({submitted.receipt.status})")

        print()
        print(f"STEP {index * 2} · ADJUDICATION")
        precedent = registry.get_precedent(" ".join(facts), "digital-commerce", 3)
        if not precedent:
            print("    precedent retrieved: none — cold start, this becomes the first holding")
        for hit in precedent:
            print(
                f"    precedent retrieved: {hit.holding_id}  "
                f"similarity {hit.similarity:.2f}  authority {hit.authority_bp / 10_000:.2f}"
            )

        try:
            adjudicated = registry.adjudicate(case_id, sender=registry.adjudicator_address)
        except AdapterError as error:
            print(f"\n    ADJUDICATION REJECTED: {error}")
            return 1

        case = registry.get_case(case_id)
        print(f"    verdict        {case.verdict}")
        print(f"    ratio          {case.ratio}")
        if case.precedent_used:
            disposition = "DISTINGUISHES" if case.distinguished else "FOLLOWS"
            print(f"    disposition    {disposition} {', '.join(case.precedent_used)}")
            if case.distinguished:
                print(wrap(f"because: {case.distinguishment_reason}", indent="                   "))
        else:
            print("    disposition    first impression (no precedent)")

        if args.no_settle:
            print("\n    --no-settle: stopping at acceptance; no holding is created")
            continue

        print()
        print("FINALITY")
        receipts = chain.settle(adjudicated.transaction_reference)
        for receipt in receipts:
            print(
                f"    {receipt.transaction_reference[:18]}…  status {receipt.status} "
                f"({receipt.status_code})  execution {receipt.execution_result}"
            )

        # re-read: the holding only exists once the adjudication has finalized
        case = registry.get_case(case_id)
        holding_id = case.holding_id if case else ""
        holding = registry.get_holding(holding_id) if holding_id else None
        if holding is None:
            print("    no holding was created — the adjudication did not finalize")
            continue

        print()
        print(f"HOLDING {holding.display_id} CREATED")
        print(f"    status         {holding.status}")
        print(wrap(f"issue: {holding.issue}", indent="    "))
        print(wrap(f"ratio: {holding.ratio}", indent="    "))
        if holding.authority:
            print(
                f"    authority      {holding.authority.score:.2f} ({holding.authority.band}) — "
                f"{holding.authority.explanation.split('. ')[1] if '.' in holding.authority.explanation else ''}"
            )
        print(f"    provenance     case {holding.provenance.case_id} · tx {holding.provenance.source_tx}")

    heading("RESULT")
    stats = registry.stats()
    print(f"    holdings {stats.total}  (final {stats.final}, pending {stats.pending}, rejected {stats.rejected})")
    print(f"    citation edges {stats.citations}  (follows {stats.follows}, distinguishes {stats.distinguishes})")
    print()
    for holding in registry.list_holdings(limit=100):
        edges = registry.get_citations(holding.holding_id)
        outgoing = [f"{edge.relationship} {edge.target_holding_id}" for edge in edges if edge.direction == "outgoing"]
        incoming = [f"{edge.relationship}← {edge.source_holding_id}" for edge in edges if edge.direction == "incoming"]
        related = ", ".join(outgoing + incoming) or "—"
        print(f"    HOLDING {holding.display_id}  {holding.verdict:<9} {holding.status:<7} {related}")

    print()
    print(wrap(
        "Every record above was produced by the contract logic. In DEMO mode there is no "
        "GenLayer consensus, no chain and no LLM call — these are simulated cases, not "
        "historical GenLayer adjudications.",
        indent="    ",
    ))
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
