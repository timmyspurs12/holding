"""The contract and the shared core must not drift.

A GenLayer contract is deployed as one file, so the deterministic core is
duplicated. These tests are the guard rail: if someone edits one copy, CI fails.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"


def _block(path: Path, begin: str, end: str) -> str:
    text = path.read_text(encoding="utf-8")
    start = text.index(begin)
    stop = text.index(end) + len(end)
    return text[start:stop].strip()


def _strip(text: str) -> str:
    """Normalise whitespace so only real differences count."""
    return "\n".join(" ".join(line.split()) for line in text.strip().splitlines() if line.strip())


def test_generated_contract_is_up_to_date():
    result = subprocess.run(
        [sys.executable, str(SCRIPTS / "render_contract.py"), "--check"],
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    assert result.returncode == 0, (
        "contracts/HoldingRegistry.py is stale. Run: python scripts/render_contract.py\n"
        + result.stdout
    )


def test_mirrored_core_is_identical():
    shared = _block(
        ROOT / "shared" / "holding_core" / "_mirrored.py",
        "# --- BEGIN MIRRORED BLOCK (contracts/HoldingRegistry.py) ---",
        "# --- END MIRRORED BLOCK (contracts/HoldingRegistry.py) ---",
    )
    contract = _block(
        ROOT / "contracts" / "HoldingRegistry.py",
        "# --- BEGIN MIRRORED BLOCK (contracts/HoldingRegistry.py) ---",
        "# --- END MIRRORED BLOCK (contracts/HoldingRegistry.py) ---",
    )
    assert _strip(shared) == _strip(contract), "mirrored core drifted between shared/ and contracts/"


def test_mirrored_prompt_is_identical():
    shared = ROOT / "shared" / "holding_core" / "precedent.py"
    contract = ROOT / "contracts" / "Adjudicator.py"

    for constant in ("ADJUDICATION_OUTPUT_CONTRACT", "DISTINGUISHING_INSTRUCTION"):
        pattern = re.compile(rf'^{constant} = """(.*?)"""', re.DOTALL | re.MULTILINE)
        in_shared = pattern.search(shared.read_text(encoding="utf-8"))
        in_contract = pattern.search(contract.read_text(encoding="utf-8"))
        assert in_shared is not None, f"{constant} missing from precedent.py"
        assert in_contract is not None, f"{constant} missing from Adjudicator.py"
        assert in_shared.group(1).strip() == in_contract.group(1).strip(), (
            f"{constant} drifted between shared/holding_core/precedent.py and contracts/Adjudicator.py"
        )


@pytest.mark.parametrize(
    "filename",
    ["HoldingRegistry.py", "Adjudicator.py"],
)
def test_contract_files_parse(filename):
    import ast

    source = (ROOT / "contracts" / filename).read_text(encoding="utf-8")
    ast.parse(source)


def test_contract_pins_its_dependencies():
    source = (ROOT / "contracts" / "HoldingRegistry.py").read_text(encoding="utf-8")
    assert '"Depends": "py-lib-genlayermodelwrappers:' in source
    assert '"Depends": "py-genlayer:' in source
    assert "all-MiniLM-L6-v2" in source, "embedding model must be pinned, not configured"


def test_no_float_reaches_contract_state():
    """Similarity must be stored/emitted as a string — floats are unsafe in state."""
    source = (ROOT / "contracts" / "HoldingRegistry.py").read_text(encoding="utf-8")
    assert '"similarity": similarity_str' in source
    assert "similarity_to_bp(similarity_str)" in source
