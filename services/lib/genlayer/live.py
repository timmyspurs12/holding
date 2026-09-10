"""Live mode — GenLayer RPC through genlayer-py.

Nothing here is simulated. If the SDK, the RPC or the configuration is missing
the adapter raises LiveUnavailable and the API reports the mode as
misconfigured; it never silently falls back to demo data.

Pinned against genlayer-py 0.18.0 (see requirements.txt). Consensus v0.6 fee
fields are NOT available at that version, so no fee arguments are sent.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from .base import AdapterError, Chain, LiveUnavailable
from .config import GenLayerConfig
from .types import TX_EXECUTION_SUCCESS, TX_STATUS_FINALIZED, TxReceipt, WriteResult

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
            from genlayer_py import create_client
        except ImportError as error:  # pragma: no cover - depends on environment
            raise LiveUnavailable(
                "genlayer-py is not installed. Install it (`pip install genlayer-py`) "
                "or run with GENLAYER_NETWORK=demo."
            ) from error

        network = self.config.network
        kwargs: Dict[str, Any] = {}
        if self.config.rpc_url:
            kwargs["rpc_url"] = self.config.rpc_url
        try:
            if network:
                return create_client(chain=network, **kwargs)
            return create_client(**kwargs)
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

    # -- writes -------------------------------------------------------
    def write(self, address: str, method: str, args: Sequence[Any] = (), sender: str = "") -> WriteResult:
        try:
            tx_hash = self.client.write_contract(
                address=address,
                function_name=method,
                args=list(args),
                account=self.account,
            )
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
            receipt = self.client.wait_for_transaction_receipt(
                transaction_hash=transaction_reference, status="FINALIZED"
            )
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

    # -- helpers ------------------------------------------------------
    @staticmethod
    def _as_hex(value) -> str:
        if isinstance(value, bytes):
            return "0x" + value.hex()
        text = str(value)
        return text if text.startswith("0x") else "0x" + text

    @staticmethod
    def _parse(raw: Any, reference: str) -> TxReceipt:
        if raw is None:
            return TxReceipt(transaction_reference=reference, simulated=False)
        data = raw if isinstance(raw, dict) else dict(getattr(raw, "items", lambda: [])())
        status_code = data.get("status") or data.get("status_code")
        try:
            status_code = int(status_code) if status_code is not None else None
        except (TypeError, ValueError):
            status_code = None
        execution = (
            data.get("result", {}).get("execution_result")
            if isinstance(data.get("result"), dict)
            else None
        ) or data.get("execution_result") or ""
        consensus = data.get("consensus_data") or {}
        if isinstance(consensus, dict):
            finality = consensus.get("finality_timestamp") or consensus.get("finality_window_end")
        else:
            finality = getattr(consensus, "finality_timestamp", None)
        return TxReceipt(
            transaction_reference=reference,
            status_code=status_code,
            status=STATUS_NAMES.get(status_code, str(status_code)),
            execution_result=str(execution),
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
