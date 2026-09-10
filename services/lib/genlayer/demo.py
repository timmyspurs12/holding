"""DEMO mode — the real contract logic, executed locally.

What this is
------------
The contract files in /contracts are loaded and executed for real: validation,
dedupe, finality gating, VecDB retrieval, authority maths and the citation graph
all run exactly as they would on GenLayer.

What this is NOT
----------------
There is no consensus, no validator committee, no appeal window, no chain and no
LLM call. Where the contract asks for a model, a deterministic scripted
responder answers (see `scripted_adjudication`). Where GenLayer would take
minutes to finalize, `settle()` does it immediately.

Every artefact produced here carries `simulated: true` and a `DEMO` provenance
mode, and the API stamps the same on its responses. Simulated cases are never
presented as historical GenLayer cases.
"""

from __future__ import annotations

import importlib.util
import time
import typing
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .base import Chain, ContractRejected
from .config import DEMO_ADJUDICATOR, DEMO_REGISTRY, GenLayerConfig
from .types import TX_EXECUTION_SUCCESS, TX_STATUS_FINALIZED, TxReceipt, WriteResult

ROOT = Path(__file__).resolve().parents[3]
CONTRACTS = ROOT / "contracts"
RUNTIME = ROOT / "services" / "lib" / "genlayer" / "stub_runtime.py"

OWNER = "0x1111111111111111111111111111111111111111"
ATTESTOR = "0x2222222222222222222222222222222222222222"

# Simulated transaction references are valid hex but visibly marked.
TX_PREFIX = "0xdef1"


def _load_runtime():
    """Install the development runtime double as the importable `genlayer` module."""
    existing = __import__("sys").modules.get("genlayer")
    if existing is not None and getattr(existing, "_holding_runtime_double", False):
        return existing
    import sys

    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    spec = importlib.util.spec_from_file_location("genlayer", RUNTIME)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    sys.modules["genlayer"] = module

    import types

    numpy_stub = types.ModuleType("numpy")
    numpy_stub.float32 = module.np.float32
    sys.modules["numpy"] = numpy_stub

    wrappers = types.ModuleType("genlayermodelwrappers")
    wrappers.SentenceTransformer = module.genlayermodelwrappers.SentenceTransformer
    sys.modules["genlayermodelwrappers"] = wrappers
    return module


def load_contract(name: str):
    path = CONTRACTS / f"{name}.py"
    if not path.exists():
        raise ContractRejected(
            f"contract {name} not found — run `python scripts/render_contract.py` first"
        )
    spec = importlib.util.spec_from_file_location(f"runtime_{name}", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _storage_defaults(runtime, cls) -> Dict[str, Any]:
    defaults: Dict[str, Any] = {}
    for base in reversed(cls.__mro__):
        for name, annotation in getattr(base, "__annotations__", {}).items():
            if name.startswith("_"):
                continue
            origin = typing.get_origin(annotation) or annotation
            if origin is runtime.TreeMap:
                defaults[name] = runtime.TreeMap()
            elif origin is runtime.DynArray:
                defaults[name] = runtime.DynArray()
            elif origin is runtime.VecDB:
                defaults[name] = runtime.VecDB()
            else:
                defaults[name] = None
    return defaults


# ---------------------------------------------------------------------------
# the scripted model
# ---------------------------------------------------------------------------
MATERIAL_DIFFERENCE_MARKERS = (
    "fully delivered",
    "delivered in full",
    "already delivered",
    "delivered before cancellation",
    "non-refundable",
    "expressly excluded",
)

GENERIC_RATIO = (
    "Where a digital service is partially consumed and no usage-based exclusion applies, "
    "a pro rata refund is owed for the unconsumed share."
)

DISTINGUISHING_RATIO = (
    "Where the entitlement has already been delivered in full before cancellation, the "
    "partial-consumption refund rule does not apply."
)


def detect_material_difference(facts: Sequence[str]) -> str:
    """Return the material-difference marker found in the facts, else ''."""
    joined = " ".join(facts).lower()
    for marker in MATERIAL_DIFFERENCE_MARKERS:
        if marker in joined:
            return marker
    return ""


def scripted_adjudication(prompt: str) -> Dict[str, Any]:
    """Deterministic stand-in for the LLM, used only in DEMO mode.

    Reads the prompt the contract built: if precedent was retrieved it either
    follows the nearest holding or distinguishes it on a concrete material
    difference found in the facts. No network call is made and no randomness is
    involved, so the leader and the validator "runs" agree.
    """
    facts = _prompt_facts(prompt)
    precedents = _prompt_precedents(prompt)
    issue = _prompt_field(prompt, "ISSUE") or (
        "Refund eligibility after partial consumption of a digital service"
    )

    if not precedents:
        return _payload(
            issue=issue,
            verdict="APPROVED",
            ratio=GENERIC_RATIO,
            codes=["PARTIAL_CONSUMPTION"],
            used=[],
            distinguished=False,
            reason="",
            reasoning="No precedent was retrieved, so this is a first-impression holding.",
        )

    nearest = precedents[0]
    marker = detect_material_difference(facts)
    if marker:
        return _payload(
            issue=issue,
            verdict="REJECTED",
            ratio=DISTINGUISHING_RATIO,
            codes=["FULL_DELIVERY"],
            used=[nearest],
            distinguished=True,
            reason=(
                f"Unlike {nearest}, the entitlement had been {marker} before cancellation, "
                "so the partial-consumption rule that governed that holding is not triggered here."
            ),
            reasoning=(
                f"The nearest holding {nearest} governs partial consumption, but this case "
                f"involves an entitlement that was {marker}; that material difference defeats the analogy."
            ),
        )

    return _payload(
        issue=issue,
        verdict="APPROVED",
        ratio=GENERIC_RATIO,
        codes=["PARTIAL_CONSUMPTION"],
        used=[nearest],
        distinguished=False,
        reason="",
        reasoning=(
            f"No material difference separates this case from {nearest}, so the panel "
            "follows it and applies the same rule."
        ),
    )


def _payload(*, issue, verdict, ratio, codes, used, distinguished, reason, reasoning):
    return {
        "issue": issue,
        "facts": ["fact supplied by the submitting contract"],
        "verdict": verdict,
        "ratio": ratio,
        "reason_codes": codes,
        "precedent_used": used,
        "followed": not distinguished,
        "distinguished": distinguished,
        "distinguishment_reason": reason,
        "reasoning": reasoning,
    }


def _section(prompt: str, header: str) -> str:
    if header not in prompt:
        return ""
    tail = prompt.split(header, 1)[1]
    for stop in ("\n\n", "\nRETRIEVED PRECEDENT"):
        if stop in tail:
            tail = tail.split(stop, 1)[0]
    return tail.strip()


def _prompt_facts(prompt: str) -> List[str]:
    block = _section(prompt, "MATERIAL FACTS")
    return [line[2:].strip() for line in block.splitlines() if line.startswith("- ")]


def _prompt_precedents(prompt: str) -> List[str]:
    if "RETRIEVED PRECEDENT" not in prompt:
        return []
    block = prompt.split("RETRIEVED PRECEDENT", 1)[1]
    out: List[str] = []
    for token in block.replace("\n", " ").split():
        token = token.strip(",.;:()[]")
        if token.startswith("HLD-") and len(token) == 10:
            out.append(token)
    return out


def _prompt_field(prompt: str, header: str) -> str:
    raw = _section(prompt, header)
    return " ".join(raw.split())


# ---------------------------------------------------------------------------
# the demo chain
# ---------------------------------------------------------------------------
class DemoChain(Chain):
    """Executes contracts in-process and settles them on demand."""

    def __init__(self, config: GenLayerConfig) -> None:
        super().__init__(config)
        self.runtime = _load_runtime()
        self.gl = self.runtime.gl
        self._contracts: Dict[str, Any] = {}
        self._pending: Dict[str, List[Dict[str, Any]]] = {}  # tx -> queued emits
        self._receipts: Dict[str, TxReceipt] = {}
        self._counter = 0

        registry_module = load_contract("HoldingRegistry")
        self.registry = self._instantiate(
            registry_module.HoldingRegistry, OWNER, address=config.registry_address or DEMO_REGISTRY
        )
        with self._as(OWNER):
            self.registry.register_attestor(ATTESTOR, True)

        adjudicator_module = load_contract("Adjudicator")
        self.adjudicator = self._instantiate(
            adjudicator_module.PrecedentAdjudicator,
            config.registry_address or DEMO_REGISTRY,
            "digital-commerce",
            "RefundArbiter",
            5,
            address=config.adjudicator_address or DEMO_ADJUDICATOR,
        )
        with self._as(OWNER):
            self.registry.register_source(config.adjudicator_address or DEMO_ADJUDICATOR, True)

        # DEMO mode replaces the model with the scripted responder.
        self.gl.nondet.queued_prompt_response = scripted_adjudication

    # -- internals -----------------------------------------------------
    def _instantiate(self, cls, *args, address: str):
        instance = object.__new__(cls)
        for key, value in _storage_defaults(self.runtime, cls).items():
            setattr(instance, key, value)
        instance.__init__(*args)
        self.gl._registry[str(address)] = instance
        instance._stub_address = str(address)
        return instance

    def _target(self, address: str):
        instance = self.gl._registry.get(str(address))
        if instance is None:
            raise ContractRejected(f"demo chain: no contract deployed at {address}")
        return instance

    @contextmanager
    def _as(self, address: str):
        previous = self.gl.message.sender_address
        self.gl.message.sender_address = self.runtime.Address(address)
        try:
            yield
        finally:
            self.gl.message.sender_address = previous

    def _next_tx(self) -> str:
        self._counter += 1
        return f"{TX_PREFIX}{self._counter:060x}"

    # -- reads ---------------------------------------------------------
    def read(self, address: str, method: str, args: Sequence[Any] = ()) -> Any:
        target = self._target(address)
        function = getattr(target, method, None)
        if function is None:
            raise ContractRejected(f"demo chain: {method} is not a method of the contract at {address}")
        try:
            return function(*list(args))
        except self.gl.UserError as error:
            raise ContractRejected(str(error)) from error

    # -- writes --------------------------------------------------------
    def write(self, address: str, method: str, args: Sequence[Any] = (), sender: str = "") -> WriteResult:
        target = self._target(address)
        function = getattr(target, method, None)
        if function is None:
            raise ContractRejected(f"demo chain: {method} is not a method of the contract at {address}")

        before = self.runtime._Emitter.instances
        self.runtime._Emitter.instances = []
        tx = self._next_tx()
        sender_address = sender or getattr(target, "_stub_address", address)
        try:
            with self._as(sender_address):
                result = function(*list(args))
        except self.gl.UserError as error:
            self.runtime._Emitter.instances = before
            raise ContractRejected(str(error)) from error

        queued = [
            {
                # the contract the message was addressed to, not the one that sent it
                "target": str(getattr(emitter.target, "_stub_address", address)),
                "source": str(address),
                "method": call["method"],
                "args": call["args"],
                "kwargs": call["kwargs"],
            }
            for emitter in self.runtime._Emitter.instances
            if emitter.on == "finalized"
            for call in emitter.calls
        ]
        self.runtime._Emitter.instances = before
        self._pending[tx] = queued

        receipt = TxReceipt(
            transaction_reference=tx,
            status_code=5,  # Accepted — provisional until the appeal window closes
            status="ACCEPTED",
            execution_result=TX_EXECUTION_SUCCESS,
            finality_timestamp=None,
            simulated=True,
        )
        self._receipts[tx] = receipt
        return WriteResult(transaction_reference=tx, method=method, receipt=receipt, result=result, simulated=True)

    def settle(self, transaction_reference: str) -> List[TxReceipt]:
        """Deliver the queued finalize-time messages and attest the results.

        Models: appeal window closes -> transaction finalizes -> the emitted
        `create_holding` lands -> an attestor attests status 7 + a successful
        execution result -> pending relationship intents materialise into
        citation edges.
        """
        queued = self._pending.pop(transaction_reference, [])
        now = int(time.time())
        created: List[str] = []
        for message in queued:
            target = self._target(message["target"])
            function = getattr(target, message["method"])
            with self._as(message["source"]):
                outcome = function(*message["args"], **message["kwargs"])
            if message["method"] == "create_holding" and isinstance(outcome, str):
                created.append(outcome)

        receipts: List[TxReceipt] = []
        for holding_id in created:
            with self._as(ATTESTOR):
                status = self.registry.attest_finality(
                    holding_id, TX_STATUS_FINALIZED, TX_EXECUTION_SUCCESS, now, "NONE", transaction_reference
                )
            receipts.append(
                TxReceipt(
                    transaction_reference=transaction_reference,
                    status_code=TX_STATUS_FINALIZED,
                    status="FINALIZED",
                    execution_result=TX_EXECUTION_SUCCESS,
                    finality_timestamp=now,
                    consensus_data={"holding_id": holding_id, "holding_status": status, "simulated": True},
                    simulated=True,
                )
            )

        receipt = TxReceipt(
            transaction_reference=transaction_reference,
            status_code=TX_STATUS_FINALIZED,
            status="FINALIZED",
            execution_result=TX_EXECUTION_SUCCESS,
            finality_timestamp=now,
            consensus_data={"settled_holdings": created, "simulated": True},
            simulated=True,
        )
        self._receipts[transaction_reference] = receipt
        return receipts or [receipt]

    def receipt(self, transaction_reference: str) -> TxReceipt:
        receipt = self._receipts.get(transaction_reference)
        if receipt is None:
            raise ContractRejected(f"demo chain: unknown transaction {transaction_reference}")
        return receipt
