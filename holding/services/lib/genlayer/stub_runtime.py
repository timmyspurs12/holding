"""A test double for the GenLayer / GenVM runtime.

WHY THIS EXISTS
---------------
The HoldingRegistry is a GenLayer Intelligent Contract. It can only truly execute
inside GenVM. Running a real node is not possible in this environment, so this
module stubs the runtime surface the contract touches and lets the contract's own
logic be executed and asserted in-process.

WHAT IT DOES AND DOES NOT PROVE
-------------------------------
It DOES prove: the contract's state machine, authorisation rules, validation,
dedupe, cold-start behaviour, filtering, ordering, and the authority arithmetic —
because all of that is ordinary Python the contract carries.

It does NOT prove: GenVM consensus behaviour, real embedding values, gas/fees, or
on-chain deployment. Similarity values in tests come from a deterministic hashing
embedder substituted for the pinned `all-MiniLM-L6-v2` model. Nothing in this
directory should be read as evidence of live network behaviour.

The stub is injected by `tests/conftest.py`; production code never imports it.
"""

from __future__ import annotations

_holding_runtime_double = True  # marker: this module is a development double, not the GenVM runtime

import math
from dataclasses import dataclass as _stdlib_dataclass
from typing import Any, Dict, Iterable, List

__all__ = [
    "gl",
    "Address",
    "u256",
    "TreeMap",
    "DynArray",
    "VecDB",
    "allow_storage",
    "dataclass",
    "np",
    "genlayermodelwrappers",
]


# ---------------------------------------------------------------------------
# types
# ---------------------------------------------------------------------------
class u256(int):
    """Integer type used for on-chain numerics. Kept as int for determinism."""

    __slots__ = ()


class Address(str):
    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - cosmetics
        return f"Address({str(self)})"


class TreeMap(dict):
    """Dict-backed ordered map with the TreeMap access pattern used in contracts."""

    def get(self, key, default=None):  # type: ignore[override]
        return dict.get(self, key, default)


class DynArray(list):
    def append(self, item):  # type: ignore[override]
        list.append(self, item)


def allow_storage(cls):
    return cls


def dataclass(cls=None, **kwargs):
    def wrap(c):
        return _stdlib_dataclass(c)

    return wrap(cls) if cls is not None else wrap


class _VecDBMeta(type):
    def __getitem__(cls, item):  # VecDB[np.float32, Literal[384], StoreValue]
        return cls


class VecDB(metaclass=_VecDBMeta):
    """In-memory k-NN store with cosine distance, matching the GenVM VecDB API
    surface used by the contract (`insert`, `knn`, `remove`, iteration)."""

    def __init__(self) -> None:
        self._items: List[Dict[str, Any]] = []

    def insert(self, key, value) -> None:
        self._items.append({"key": list(float(x) for x in key), "value": value})

    def knn(self, key, k: int):
        query = list(float(x) for x in key)
        scored = []
        for item in self._items:
            scored.append((_cosine_distance(query, item["key"]), item))
        scored.sort(key=lambda pair: (pair[0], str(getattr(pair[1]["value"], "holding_id", ""))))
        return [_KNNResult(item["key"], item["value"], dist) for dist, item in scored[:k]]

    def remove(self, key) -> None:  # pragma: no cover - unused by the contract today
        self._items = [i for i in self._items if i["key"] != list(key)]

    def __iter__(self):
        for item in self._items:
            yield _KNNResult(item["key"], item["value"], 0.0)

    def __len__(self) -> int:
        return len(self._items)


class _KNNResult:
    __slots__ = ("key", "value", "distance")

    def __init__(self, key, value, distance: float) -> None:
        self.key = key
        self.value = value
        self.distance = distance

    def remove(self) -> None:
        raise NotImplementedError("stub: removal is performed on the owning store")


def _cosine_distance(a: Iterable[float], b: Iterable[float]) -> float:
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na == 0.0 or nb == 0.0:
        return 1.0
    return 1.0 - (dot / (math.sqrt(na) * math.sqrt(nb)))


# ---------------------------------------------------------------------------
# numpy + embedding model doubles
# ---------------------------------------------------------------------------
class _NumpyStub:
    float32 = float


np = _NumpyStub()


class _DeterministicEmbedder:
    """Deterministic hashing embedder used *instead of* all-MiniLM-L6-v2 in tests.

    It preserves the properties the contract depends on (same text -> same vector,
    similar text -> close vector) so ordering logic can be tested. It is NOT the
    on-chain model and its similarity values are not real.
    """

    DIM = 384

    def __call__(self, text: str):
        import hashlib

        vector = [0.0] * self.DIM
        tokens = "".join(c.lower() if c.isalnum() else " " for c in str(text)).split()
        if not tokens:
            return vector
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            for slot in range(0, 8):
                idx = (digest[slot * 2] * 256 + digest[slot * 2 + 1]) % self.DIM
                sign = 1.0 if digest[slot] % 2 == 0 else -1.0
                vector[idx] += sign
            # a crude bigram component so word order has a small effect
            for slot in range(0, 4):
                idx = (digest[slot] * 7 + slot * 31) % self.DIM
                vector[idx] += 0.5
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]


class _ModelWrappers:
    SentenceTransformer = staticmethod(lambda model_id: _DeterministicEmbedder())


genlayermodelwrappers = _ModelWrappers()


# ---------------------------------------------------------------------------
# gl namespace
# ---------------------------------------------------------------------------
class UserError(Exception):
    pass


class _Return:
    def __init__(self, calldata):
        self.calldata = calldata


class _Message:
    sender_address: Any = None
    contract_address: Any = Address("0xADJUDICATOR")
    timestamp: int = 0


class _VM:
    Return = _Return
    UserError = UserError

    @staticmethod
    def run_nondet_unsafe(leader_fn, validator_fn):
        """Single-validator approximation of the equivalence principle.

        The leader runs once, then the supplied validator is executed against the
        wrapped leader result — so a contract's validator logic (independent
        re-run + comparison of decision fields) is genuinely exercised. If the
        validator rejects, no result is returned, mirroring a failed round.

        It does NOT model committees, rotations, appeals or non-determinism.
        """
        result = leader_fn()
        if not validator_fn(_Return(result)):
            raise UserError("stub: validators rejected the leader result")
        return result


class _Nondet:
    """Non-deterministic operation surface. Tests queue responses explicitly."""

    queued_prompt_response: Any = None
    prompt_calls: List[str] = []

    @classmethod
    def exec_prompt(cls, prompt: str, response_format: str = None, images=None):
        cls.prompt_calls.append(prompt)
        if cls.queued_prompt_response is None:
            raise AssertionError(
                "genlayer stub: no LLM response queued. "
                "Use stub_llm_response() in the test to queue one."
            )
        response = cls.queued_prompt_response
        if callable(response):
            response = response(prompt)
        return response


class _Emitter:
    """Records `contract.emit(on=...).method(args)` calls for assertions."""

    instances: List["_Emitter"] = []

    def __init__(self, target, on: str) -> None:
        self.target = target
        self.on = on
        self.calls: List[Dict[str, Any]] = []
        _Emitter.instances.append(self)

    def __getattr__(self, name: str):
        def call(*args, **kwargs):
            self.calls.append({"method": name, "args": args, "kwargs": kwargs, "on": self.on})
            return _Pending(self, name, args, kwargs)

        return call


class _Pending:
    def __init__(self, emitter: _Emitter, method: str, args, kwargs) -> None:
        self.emitter = emitter
        self.method = method
        self.args = args
        self.kwargs = kwargs

    def execute(self):
        fn = getattr(self.emitter.target, self.method)
        return fn(*self.args, **self.kwargs)


class _ContractHandle:
    def __init__(self, instance) -> None:
        self._instance = instance

    def view(self):
        return self._instance

    def emit(self, on: str = "accepted", value: int = 0):
        if on not in ("accepted", "finalized"):
            raise UserError(f"stub: invalid emit target {on!r}")
        return _Emitter(self._instance, on)


class _GL:
    Contract = object
    UserError = UserError
    message = _Message()
    vm = _VM()
    nondet = _Nondet  # class, so tests can set queued responses on the shared surface

    # decorators
    @staticmethod
    def public_view(fn):
        fn.__is_view__ = True
        return fn

    @staticmethod
    def public_write(fn):
        fn.__is_write__ = True
        return fn

    class public:
        view = staticmethod(lambda fn: _GL.public_view(fn))
        write = staticmethod(lambda fn: _GL.public_write(fn))

    @staticmethod
    def get_contract_at(address):
        instance = _GL._registry.get(str(address))
        if instance is None:
            raise UserError(f"stub: no contract registered at {address}")
        return _ContractHandle(instance)

    _registry: Dict[str, Any] = {}


gl = _GL()
