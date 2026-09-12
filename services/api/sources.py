"""Source-contract registration proposals.

A registered source is the only thing allowed to emit holdings into the
canonical registry, so it cannot be self-service. The flow is deliberately two
sided:

    wallet  ->  POST /operator/source-contracts     status: PENDING
    operator ->  POST /admin/source-contracts/{id}/approve   -> contract.register_source()

A proposal is not a holding, is not precedent, and is never returned by
/holdings. It is a request. Only an approved proposal reaches the contract, and
the approval records the transaction reference that proves it.

Storage is a small JSON file (default data/source_contracts.json, git-ignored)
so proposals survive a restart without dragging a database into the project.
The file is not the source of truth for anything canonical — the contract is.
It is the queue in front of the contract.
"""

from __future__ import annotations

import json
import os
import re
import secrets
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional

from ..lib.genlayer.config import GenLayerConfig

ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
TX_RE = re.compile(r"^0x[0-9a-fA-F]{64}$")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,47}$")

PENDING = "PENDING"
APPROVED = "APPROVED"
REJECTED = "REJECTED"
STATUSES = (PENDING, APPROVED, REJECTED)


class ProposalError(ValueError):
    """A proposal payload failed validation."""


@dataclass
class SourceProposal:
    proposal_id: str
    contract_address: str
    domain: str
    contract_class: str
    label: str
    submitted_by: str
    submitted_at: int
    status: str = PENDING
    deploy_tx: str = ""
    notes: str = ""
    decided_at: Optional[int] = None
    decided_by: str = ""
    decision_note: str = ""
    transaction_reference: Optional[str] = None
    simulated: bool = True

    def public(self) -> Dict[str, object]:
        """What anyone may read. There is no private contact data stored."""
        data = asdict(self)
        data["short_address"] = f"{self.contract_address[:6]}…{self.contract_address[-4:]}"
        return data


def validate_proposal_input(
    *,
    contract_address: str,
    domain: str,
    contract_class: str,
    label: str = "",
    deploy_tx: str = "",
    notes: str = "",
) -> Dict[str, str]:
    errors: List[str] = []

    address = (contract_address or "").strip()
    if not ADDRESS_RE.match(address):
        errors.append("contract_address must be a 0x-prefixed 20-byte address")
    elif address.lower().startswith("0xdemo"):
        errors.append("contract_address cannot be a DEMO placeholder address")

    domain_value = (domain or "").strip().lower()
    if not SLUG_RE.match(domain_value):
        errors.append("domain must be 2-48 chars, lowercase letters/digits/hyphen")

    class_value = (contract_class or "").strip()
    if not SLUG_RE.match(class_value.lower()):
        errors.append("contract_class must be 2-48 chars, lowercase letters/digits/hyphen")

    label_value = (label or "").strip()
    if len(label_value) > 80:
        errors.append("label must be 80 characters or fewer")

    tx_value = (deploy_tx or "").strip()
    if tx_value and not TX_RE.match(tx_value):
        errors.append("deploy_tx must be a 0x-prefixed 32-byte transaction hash")

    notes_value = (notes or "").strip()
    if len(notes_value) > 500:
        errors.append("notes must be 500 characters or fewer")

    if errors:
        raise ProposalError("; ".join(errors))

    return {
        "contract_address": address.lower(),
        "domain": domain_value,
        "contract_class": class_value,
        "label": label_value,
        "deploy_tx": tx_value,
        "notes": notes_value,
    }


class SourceContractStore:
    """Thread-safe proposal queue with an optional JSON file behind it."""

    def __init__(self, path: Optional[str] = None) -> None:
        self.path = Path(path or os.getenv("HOLDING_SOURCES_DB", "data/source_contracts.json"))
        self._lock = threading.RLock()
        self._items: Dict[str, SourceProposal] = {}
        self._load()

    # -- persistence ---------------------------------------------------
    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        for entry in raw if isinstance(raw, list) else []:
            try:
                proposal = SourceProposal(**entry)
            except TypeError:
                continue
            self._items[proposal.proposal_id] = proposal

    def _save(self) -> None:
        if not self.path.parent.exists():
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
            except OSError:  # pragma: no cover - read-only filesystem
                return
        try:
            payload = [asdict(item) for item in self._items.values()]
            self.path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        except OSError:  # pragma: no cover - persistence is best effort
            pass

    # -- reads ---------------------------------------------------------
    def get(self, proposal_id: str) -> Optional[SourceProposal]:
        with self._lock:
            return self._items.get(proposal_id)

    def list(self, *, status: str = "", address: str = "") -> List[SourceProposal]:
        with self._lock:
            items = list(self._items.values())
        if status:
            wanted = status.upper()
            items = [item for item in items if item.status == wanted]
        if address:
            wanted_address = address.lower()
            items = [item for item in items if item.submitted_by == wanted_address]
        return sorted(items, key=lambda item: (-item.submitted_at, item.proposal_id))

    def duplicate_of(self, contract_address: str, config: GenLayerConfig) -> Optional[SourceProposal]:
        """An already-live or still-pending proposal for this contract."""
        wanted = contract_address.lower()
        for item in self.list():
            if item.contract_address == wanted and item.status in (PENDING, APPROVED):
                return item
        return None

    # -- writes --------------------------------------------------------
    def propose(self, *, submitted_by: str, simulated: bool, **fields) -> SourceProposal:
        with self._lock:
            proposal = SourceProposal(
                proposal_id=f"SRC-{secrets.token_hex(3).upper()}",
                submitted_by=submitted_by.lower(),
                submitted_at=int(time.time()),
                simulated=simulated,
                **fields,
            )
            self._items[proposal.proposal_id] = proposal
            self._save()
            return proposal

    def decide(
        self,
        proposal_id: str,
        *,
        status: str,
        decided_by: str,
        note: str = "",
        transaction_reference: Optional[str] = None,
    ) -> SourceProposal:
        if status not in (APPROVED, REJECTED):
            raise ProposalError(f"invalid decision {status!r}")
        with self._lock:
            proposal = self._items.get(proposal_id)
            if proposal is None:
                raise KeyError(proposal_id)
            if proposal.status != PENDING:
                raise ProposalError(f"proposal {proposal_id} is already {proposal.status}")
            proposal.status = status
            proposal.decided_at = int(time.time())
            proposal.decided_by = decided_by
            proposal.decision_note = note
            proposal.transaction_reference = transaction_reference
            self._save()
            return proposal
