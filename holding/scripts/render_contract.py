#!/usr/bin/env python3
"""Render contracts/HoldingRegistry.py from its template + the mirrored block.

A GenLayer Intelligent Contract is deployed as a single file and cannot import
local modules, so the deterministic core lives in two places. Rather than hand
copying it (and drifting), the contract is generated:

    contracts/HoldingRegistry.template.py   (contract logic)
    shared/holding_core/_mirrored.py        (pure deterministic core)
                    |
                    v
    contracts/HoldingRegistry.py            (generated, committed)

Run after editing either source:  python scripts/render_contract.py
`tests/test_mirror_sync.py` fails if the generated file is stale.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "contracts" / "HoldingRegistry.template.py"
MIRRORED = ROOT / "shared" / "holding_core" / "_mirrored.py"
OUTPUT = ROOT / "contracts" / "HoldingRegistry.py"

BEGIN = "# --- BEGIN MIRRORED BLOCK (contracts/HoldingRegistry.py) ---"
END = "# --- END MIRRORED BLOCK (contracts/HoldingRegistry.py) ---"
PLACEHOLDER = "# >>> MIRRORED BLOCK <<<"


def extract_mirrored_block(source: str) -> str:
    if BEGIN not in source or END not in source:
        raise SystemExit(f"mirrored markers not found in {MIRRORED}")
    start = source.index(BEGIN)
    end = source.index(END) + len(END)
    return source[start:end].rstrip("\n")


def render() -> str:
    template = TEMPLATE.read_text(encoding="utf-8")
    mirrored = extract_mirrored_block(MIRRORED.read_text(encoding="utf-8"))
    if PLACEHOLDER not in template:
        raise SystemExit(f"placeholder {PLACEHOLDER!r} not found in {TEMPLATE}")
    return template.replace(PLACEHOLDER, mirrored)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="exit 1 if the generated contract is stale")
    args = parser.parse_args()

    rendered = render()
    current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else None

    if args.check:
        if current == rendered:
            print("contracts/HoldingRegistry.py is up to date")
            return 0
        print("contracts/HoldingRegistry.py is STALE — run: python scripts/render_contract.py")
        return 1

    OUTPUT.write_text(rendered, encoding="utf-8")
    print(f"rendered {OUTPUT.relative_to(ROOT)} ({len(rendered.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
