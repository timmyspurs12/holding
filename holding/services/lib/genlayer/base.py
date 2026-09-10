"""The chain interface every backend mode implements (genlayerClient).

Two implementations exist:

  DemoChain  — runs the real contract code in a local development runtime.
               No consensus, no chain, no model call. Clearly labelled.
  LiveChain  — talks to a GenLayer RPC through genlayer-py.

Neither is allowed to fabricate finality: a transaction is final only when a
status-7 receipt with a FINISHED_WITH_RETURN execution result says so (live), or
after DemoChain.settle() has explicitly settled it (demo, labelled simulated).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Sequence

from .config import GenLayerConfig
from .types import NetworkMode, TxReceipt, WriteResult


class AdapterError(RuntimeError):
    """The adapter cannot serve the request (misconfiguration or unavailable)."""


class LiveUnavailable(AdapterError):
    """A live capability was requested but the environment cannot provide it."""


class ContractRejected(AdapterError):
    """The contract raised a UserError — the request was rejected on purpose."""


class Chain(ABC):
    def __init__(self, config: GenLayerConfig) -> None:
        self.config = config

    @property
    def mode(self) -> NetworkMode:
        return self.config.mode

    @property
    def simulated(self) -> bool:
        return self.config.mode is NetworkMode.DEMO

    # -- reads ---------------------------------------------------------
    @abstractmethod
    def read(self, address: str, method: str, args: Sequence[Any] = ()) -> Any:
        """Call a @gl.public.view method. Returns decoded data."""

    # -- writes --------------------------------------------------------
    @abstractmethod
    def write(self, address: str, method: str, args: Sequence[Any] = (), sender: str = "") -> WriteResult:
        """Submit a state-changing call. Returns at acceptance, not finality."""

    @abstractmethod
    def settle(self, transaction_reference: str) -> List[TxReceipt]:
        """Drive a submitted transaction to finality.

        Live: wait for the appeal window and the finalize step, then read the
        receipt. Demo: deliver the queued `emit(on='finalized')` messages and
        attest the resulting records, both labelled simulated.
        """

    @abstractmethod
    def receipt(self, transaction_reference: str) -> TxReceipt:
        """Read the current receipt for a transaction."""

    # -- convenience ---------------------------------------------------
    def call_view(self, address: str, method: str, *args: Any) -> Any:
        return self.read(address, method, list(args))

    def submit(self, address: str, method: str, *args: Any, sender: str = "") -> WriteResult:
        return self.write(address, method, list(args), sender=sender)

    def health(self) -> Dict[str, Any]:
        return {
            "mode": self.mode.value,
            "network": self.config.network,
            "simulated": self.simulated,
            "registry_address": self.config.registry_address,
        }
