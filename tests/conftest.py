"""Pytest harness for executing GenLayer contract logic locally.

Installs the runtime double (services/lib/genlayer/stub_runtime.py) into sys.modules, loads the
generated contract files, and provides fixtures that instantiate them with their
storage initialised.

See services/lib/genlayer/stub_runtime.py for what the double does and does not prove.
"""

from __future__ import annotations

import importlib.util
import sys
import types
import typing
from contextlib import contextmanager
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CONTRACTS = ROOT / "contracts"


def _load_stub_modules() -> types.ModuleType:
    """Register the runtime test double as the importable `genlayer` package."""
    if "genlayer" in sys.modules:
        return sys.modules["genlayer"]

    spec = importlib.util.spec_from_file_location(
        "genlayer", ROOT / "services" / "lib" / "genlayer" / "stub_runtime.py"
    )
    stub = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(stub)
    sys.modules["genlayer"] = stub

    numpy_stub = types.ModuleType("numpy")
    numpy_stub.float32 = stub.np.float32
    sys.modules["numpy"] = numpy_stub

    wrappers = types.ModuleType("genlayermodelwrappers")
    wrappers.SentenceTransformer = stub.genlayermodelwrappers.SentenceTransformer
    sys.modules["genlayermodelwrappers"] = wrappers

    return stub


STUB = _load_stub_modules()
gl = STUB.gl
Address = STUB.Address

# `import genlayer` in a test resolves to this same stub module object, so
# exception classes raised inside contracts compare equal to the ones tests catch.


def load_contract(name: str):
    """Import a contract file by name (contracts/<name>.py) as a module."""
    path = CONTRACTS / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"contract_{name}", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _storage_defaults(cls) -> dict:
    defaults: dict = {}
    for base in reversed(cls.__mro__):
        for name, annotation in getattr(base, "__annotations__", {}).items():
            if name.startswith("_"):
                continue
            origin = typing.get_origin(annotation) or annotation
            if origin is STUB.TreeMap:
                defaults[name] = STUB.TreeMap()
            elif origin is STUB.DynArray:
                defaults[name] = STUB.DynArray()
            elif origin is STUB.VecDB:
                defaults[name] = STUB.VecDB()
            elif isinstance(origin, type) and issubclass(origin, (int, float, str)):
                defaults[name] = None
            else:
                defaults[name] = None
    return defaults


def instantiate(contract_cls, *args, address: str = "0x0000000000000000000000000000000000000000"):
    """Create a contract instance with its storage fields initialised."""
    instance = object.__new__(contract_cls)
    for key, value in _storage_defaults(contract_cls).items():
        setattr(instance, key, value)
    instance.__init__(*args)
    gl._registry[str(address)] = instance
    instance._stub_address = str(address)
    return instance


@contextmanager
def as_sender(address: str):
    previous = gl.message.sender_address
    gl.message.sender_address = Address(address)
    try:
        yield
    finally:
        gl.message.sender_address = previous


def stub_llm_response(response):
    """Queue the response returned by gl.nondet.exec_prompt. Callable = dynamic."""
    gl.nondet.queued_prompt_response = response
    gl.nondet.prompt_calls = []
    return response


def clear_emitters():
    STUB._Emitter.instances = []


def replay(on: str = "finalized", sender: str | None = None):
    """Execute the recorded `emit(on=...)` calls against their target contract.

    Models the runtime delivering the message after the transaction finalizes.
    """
    executed = []
    for emitter in STUB._Emitter.instances:
        if emitter.on != on:
            continue
        for call in emitter.calls:
            fn = getattr(emitter.target, call["method"])
            if sender is None:
                executed.append(fn(*call["args"], **call["kwargs"]))
            else:
                with as_sender(sender):
                    executed.append(fn(*call["args"], **call["kwargs"]))
    STUB._Emitter.instances = []
    return executed


def emitted(on: str | None = None):
    calls = []
    for emitter in STUB._Emitter.instances:
        if on is None or emitter.on == on:
            calls.extend(emitter.calls)
    return calls


OWNER = "0x1111111111111111111111111111111111111111"
ATTESTOR = "0x2222222222222222222222222222222222222222"
SOURCE = "0x3333333333333333333333333333333333333333"
STRANGER = "0x9999999999999999999999999999999999999999"
REGISTRY_ADDRESS = "0xAAAA000000000000000000000000000000000001"
ADJUDICATOR_ADDRESS = "0xBBBB000000000000000000000000000000000002"


@pytest.fixture()
def registry_module():
    return load_contract("HoldingRegistry")


@pytest.fixture()
def registry(registry_module):
    clear_emitters()
    instance = instantiate(registry_module.HoldingRegistry, OWNER, address=REGISTRY_ADDRESS)
    with as_sender(OWNER):
        instance.register_attestor(ATTESTOR, True)
        # the reference adjudicator is the canonical source contract in tests
        instance.register_source(ADJUDICATOR_ADDRESS, True)
    return instance


@pytest.fixture()
def adjudicator(registry, registry_module):
    module = load_contract("Adjudicator")
    instance = instantiate(
        module.PrecedentAdjudicator,
        REGISTRY_ADDRESS,
        "digital-commerce",
        "RefundArbiter",
        5,
        address=ADJUDICATOR_ADDRESS,
    )
    with as_sender(OWNER):
        registry.register_source(ADJUDICATOR_ADDRESS, True)
    return instance


def make_final(registry, holding_id, appeal_outcome: str = "NONE", source_tx: str = "0xabc123"):
    """Helper: attest a record as finalized (status 7 + successful execution)."""
    with as_sender(ATTESTOR):
        return registry.attest_finality(holding_id, 7, "FINISHED_WITH_RETURN", 1_770_000_000, appeal_outcome, source_tx)
