"""Live mode — GenLayer RPC through genlayer-py.

Nothing here is simulated. If the SDK, the RPC or the configuration is missing
the adapter raises LiveUnavailable and the API reports the mode as
misconfigured; it never silently falls back to demo data.

Fee handling
------------
Consensus v0.6 requires every deploy and write to carry a fee payload. Those
fields only exist in genlayer-py >= 0.19.0rc1; on 0.18 and earlier none are
sent (and a v0.6 node will reject the transaction).

The adapter detects support by looking at the SDK signature rather than by
version sniffing, so it works with either:

  * genlayer-py >= 0.19  -> estimate the fee for this exact call and send it
  * genlayer-py <= 0.18  -> send the call unchanged

HOLDING_FEE_ESTIMATE=auto (default) | off
    auto — estimate and attach fees when the SDK supports them; if estimation
           fails, log and send without (older nodes still accept that).
    off  — never attach fees.
"""

from __future__ import annotations

import inspect
import logging
import os
from typing import Any, Dict, List, Optional, Sequence

from .base import AdapterError, Chain, LiveUnavailable
from .config import GenLayerConfig
from .types import TX_EXECUTION_SUCCESS, TX_STATUS_FINALIZED, TxReceipt, WriteResult

# Consensus phases -> receipt status codes (genlayer-py >= 0.19 lifecycle shape)
PHASE_TO_STATUS_CODE = {
    "uninitialized": 0,
    "pending": 0,
    "proposing": 2,
    "committing": 3,
    "revealing": 4,
    "appealing": 8,
    "appeal_committing": 9,
    "appeal_revealing": 10,
}

LIFECYCLE_TO_STATUS_CODE = {
    ("decided", "accepted"): 5,
    ("decided", "undetermined"): 6,
    ("decided", "validators_timeout"): 11,
    ("decided", "leader_timeout"): 12,
    ("finalized", "accepted"): 7,
    ("finalized", "undetermined"): 6,
    ("finalized", "validators_timeout"): 11,
    ("finalized", "leader_timeout"): 12,
}

logger = logging.getLogger("holding.genlayer.live")

STATUS_NAMES = {
    0: "PENDING",
    1: "CANCELED",
    2: "PROPOSING",
    3: "COMMITTING",
    4: "REVEALING",
    5: "ACCEPTED",
    6: "UNDETERMINED",
    7: "FINALIZED",
    8: "APPEALING",
    9: "APPEAL_COMMITTING",
    10: "APPEAL_REVEALING",
    11: "VALIDATORS_TIMEOUT",
    12: "LEADER_TIMEOUT",
    13: "LEADER_REVEALING",
}


class LiveChain(Chain):
    def __init__(self, config: GenLayerConfig) -> None:
        super().__init__(config)
        self._client = None
        self._account = None

    # -- lazy construction -------------------------------------------
    @property
    def client(self):
        if self._client is None:
            self._client = self._build_client()
        return self._client

    def _build_client(self):
        try:
            from genlayer_py import chains, create_client
        except ImportError as error:  # pragma: no cover - depends on environment
            raise LiveUnavailable(
                "genlayer-py is not installed. Install it "
                "(`pip install -r requirements-live.txt`) or run with GENLAYER_NETWORK=demo."
            ) from error

        network = self.config.network
        # create_client() wants a GenLayerChain object, not its name. Passing a
        # string fails with "'str' object has no attribute 'rpc_urls'".
        chain = getattr(chains, network, None) if network else None
        kwargs: Dict[str, Any] = {}
        if self.config.rpc_url:
            kwargs["endpoint"] = self.config.rpc_url

        if chain is None:
            # No preset for this network (mainnet, or a name the SDK renamed).
            # Reaching for a different chain's consensus contract would silently
            # talk to the wrong network, so refuse instead.
            raise LiveUnavailable(
                f"genlayer-py has no chain preset named {network!r} "
                f"(available: {', '.join(n for n in dir(chains) if not n.startswith('_'))}). "
                "Set GENLAYER_NETWORK to one of those, or upgrade genlayer-py."
            )
        try:
            return create_client(chain=chain, **kwargs)
        except Exception as error:  # pragma: no cover - network dependent
            raise LiveUnavailable(f"could not create a GenLayer client for {network!r}: {error}") from error

    @property
    def account(self):
        if self._account is None:
            if not self.config.private_key:
                return None
            try:
                from genlayer_py import create_account
            except ImportError as error:  # pragma: no cover
                raise LiveUnavailable("genlayer-py is not installed") from error
            self._account = create_account(self.config.private_key)
        return self._account

    # -- reads --------------------------------------------------------
    def read(self, address: str, method: str, args: Sequence[Any] = ()) -> Any:
        try:
            return self.client.read_contract(
                address=address, function_name=method, args=list(args)
            )
        except Exception as error:  # pragma: no cover - network dependent
            raise AdapterError(f"read {method} failed: {error}") from error

    # -- fees (consensus v0.6) ----------------------------------------
    @property
    def _fee_mode(self) -> str:
        return (os.getenv("HOLDING_FEE_ESTIMATE") or "auto").strip().lower()

    def _sdk_supports_fees(self, method_name: str) -> bool:
        """Look at the signature, not the version string."""
        function = getattr(self.client, method_name, None)
        if function is None:
            return False
        try:
            return "fees" in inspect.signature(function).parameters
        except (TypeError, ValueError):  # pragma: no cover - exotic callables
            return False

    @staticmethod
    def _as_fee_payload(estimate: Any) -> Dict[str, Any]:
        """Reduce an estimate to the three keys TransactionFeeOptions wants."""
        if not isinstance(estimate, dict):
            estimate = dict(getattr(estimate, "items", lambda: [])())
        return {
            "distribution": estimate.get("distribution"),
            "feeValue": estimate.get("feeValue", estimate.get("fee_value", 0)),
            "messageAllocations": estimate.get(
                "messageAllocations", estimate.get("message_allocations", [])
            ),
        }

    def _estimate_write_fees(self, address: str, method: str, args: List[Any]) -> Optional[Dict[str, Any]]:
        if self._fee_mode == "off":
            return None
        estimator = getattr(self.client, "estimate_transaction_fees_for_write", None)
        if estimator is None:
            return None
        try:
            estimate = estimator(
                address=address,
                function_name=method,
                args=args,
                account=self.account,
            )
        except Exception as error:  # pragma: no cover - network dependent
            logger.warning("fee estimation failed for %s: %s", method, error)
            if self._fee_mode == "strict":
                raise AdapterError(f"fee estimation failed for {method}: {error}") from error
            return None
        return self._as_fee_payload(estimate)

    # -- writes -------------------------------------------------------
    def write(self, address: str, method: str, args: Sequence[Any] = (), sender: str = "") -> WriteResult:
        payload: Dict[str, Any] = {
            "address": address,
            "function_name": method,
            "args": list(args),
            "account": self.account,
        }
        if self._sdk_supports_fees("write_contract"):
            fees = self._estimate_write_fees(address, method, list(args))
            if fees is not None:
                payload["fees"] = fees
        try:
            tx_hash = self.client.write_contract(**payload)
        except Exception as error:  # pragma: no cover - network dependent
            raise AdapterError(f"write {method} failed: {error}") from error
        reference = self._as_hex(tx_hash)
        return WriteResult(
            transaction_reference=reference,
            method=method,
            receipt=self.receipt(reference),
            simulated=False,
        )

    def settle(self, transaction_reference: str) -> List[TxReceipt]:
        """Wait for a status-7 receipt, then verify the execution result.

        Consensus v0.6: status alone is not success. A receipt can be Finalized
        while the contract call failed, so both are checked.
        """
        try:
            receipt = self._wait_for_finality(transaction_reference)
        except Exception as error:  # pragma: no cover - network dependent
            raise AdapterError(f"waiting for {transaction_reference} failed: {error}") from error
        parsed = self._parse(receipt, transaction_reference)
        if not parsed.is_final:
            raise AdapterError(
                f"{transaction_reference} finalized with execution result "
                f"{parsed.execution_result!r}; no holding was created"
            )
        return [parsed]

    def receipt(self, transaction_reference: str) -> TxReceipt:
        try:
            raw = self.client.get_transaction_receipt(transaction_hash=transaction_reference)
        except Exception as error:  # pragma: no cover - network dependent
            raise AdapterError(f"receipt for {transaction_reference} unavailable: {error}") from error
        return self._parse(raw, transaction_reference)

    def _wait_for_finality(self, transaction_reference: str) -> Any:
        """Wait for finality, on either SDK generation.

        genlayer-py <= 0.18: wait_for_transaction_receipt(status="FINALIZED")
        genlayer-py >= 0.19: wait_for_transaction_receipt(wait_until="finalized")

        The parameter was renamed, so the call is chosen from the signature.
        """
        function = self.client.wait_for_transaction_receipt
        try:
            parameters = inspect.signature(function).parameters
        except (TypeError, ValueError):  # pragma: no cover - exotic callables
            parameters = {}
        if "wait_until" in parameters:
            return function(transaction_hash=transaction_reference, wait_until="finalized")
        return function(transaction_hash=transaction_reference, status="FINALIZED")

    # -- helpers ------------------------------------------------------
    @staticmethod
    def _as_hex(value) -> str:
        if isinstance(value, bytes):
            return "0x" + value.hex()
        text = str(value)
        return text if text.startswith("0x") else "0x" + text

    @classmethod
    def _status_code(cls, data: Dict[str, Any]) -> Optional[int]:
        """Read the status out of either receipt shape.

        0.18 and earlier put a numeric `status` on the receipt. 0.19 replaced it
        with a `lifecycle` block: {state, outcome} — or {stored_status, …} for
        the raw protocol view. Both are mapped onto the same numbering.
        """
        raw = data.get("status")
        if raw is None:
            raw = data.get("status_code")
        if raw is not None:
            try:
                return int(raw)
            except (TypeError, ValueError):
                return None

        lifecycle = data.get("lifecycle")
        if not isinstance(lifecycle, dict):
            return None
        if "stored_status" in lifecycle:
            try:
                return int(lifecycle["stored_status"])
            except (TypeError, ValueError):
                return None

        state = str(lifecycle.get("state") or "")
        outcome = str(lifecycle.get("outcome") or "")
        if state == "canceled":
            return 1
        if state == "processing":
            return PHASE_TO_STATUS_CODE.get(str(lifecycle.get("phase") or ""), 0)
        if state in ("decided", "finalized"):
            code = (LIFECYCLE_TO_STATUS_CODE.get((state, outcome))
                    or LIFECYCLE_TO_STATUS_CODE.get((state, "accepted")))
            return code
        return None

    @staticmethod
    def _execution_result(data: Dict[str, Any]) -> str:
        result = data.get("result")
        if isinstance(result, dict) and result.get("execution_result"):
            return str(result["execution_result"])
        for key in ("execution_result", "tx_execution_result_name", "result_name"):
            value = data.get(key)
            if value:
                return str(value)
        return ""

    @classmethod
    def _parse(cls, raw: Any, reference: str) -> TxReceipt:
        if raw is None:
            return TxReceipt(transaction_reference=reference, simulated=False)
        data = raw if isinstance(raw, dict) else dict(getattr(raw, "items", lambda: [])())
        status_code = cls._status_code(data)
        execution = cls._execution_result(data)
        consensus = data.get("consensus_data") or {}
        if isinstance(consensus, dict):
            finality = consensus.get("finality_timestamp") or consensus.get("finality_window_end")
        else:
            finality = getattr(consensus, "finality_timestamp", None)
        if finality is None:
            lifecycle = data.get("lifecycle")
            if isinstance(lifecycle, dict):
                finality = lifecycle.get("finalized_at") or lifecycle.get("evaluated_at")
        return TxReceipt(
            transaction_reference=reference,
            status_code=status_code,
            status=STATUS_NAMES.get(status_code, str(status_code)),
            execution_result=execution,
            finality_timestamp=int(finality) if finality else None,
            consensus_data=consensus if isinstance(consensus, dict) else {},
            simulated=False,
        )

    def health(self) -> Dict[str, Any]:
        info = super().health()
        try:
            stats = self.read(self.config.registry_address, "get_stats")
            info["reachable"] = bool(stats)
        except Exception as error:  # pragma: no cover - network dependent
            info["reachable"] = False
            info["error"] = str(error)
        return info
