"""Typed shapes that cross the GenLayer boundary (genlayerTypes).

These are the ONLY types the Reporter API is allowed to see. Raw contract
objects, web3 receipts and SDK models are converted here and never leak upward.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

# --------------------------------------------------------------------------
# network / modes
# --------------------------------------------------------------------------
class NetworkMode(str, Enum):
    """How the running process is connected to GenLayer.

    DEMO    — the real contract code is executed locally by a development
              runtime. No consensus, no chain, no LLM. Everything produced in
              this mode is labelled simulated.
    TESTNET — live Bradbury/Asimov testnet via genlayer-py.
    MAINNET — live mainnet via genlayer-py.
    """

    DEMO = "DEMO"
    TESTNET = "TESTNET"
    MAINNET = "MAINNET"


NETWORK_LABELS = {
    "demo": (NetworkMode.DEMO, ""),
    "localnet": (NetworkMode.DEMO, "localnet"),
    "studionet": (NetworkMode.TESTNET, "studionet"),
    "studio_devnet": (NetworkMode.TESTNET, "studio_devnet"),
    "studio-dev": (NetworkMode.TESTNET, "studio_devnet"),
    "testnet_asimov": (NetworkMode.TESTNET, "testnet_asimov"),
    "asimov": (NetworkMode.TESTNET, "testnet_asimov"),
    "bradbury": (NetworkMode.TESTNET, "testnet_bradbury"),
    "testnet_bradbury": (NetworkMode.TESTNET, "testnet_bradbury"),
    "mainnet": (NetworkMode.MAINNET, "mainnet"),
}

# GenLayer transaction status codes (consensus v0.6). 7 = Finalized.
TX_STATUS_FINALIZED = 7
TX_EXECUTION_SUCCESS = "FINISHED_WITH_RETURN"


class NetworkInfo(BaseModel):
    mode: NetworkMode
    network: str = ""
    chain_id: Optional[int] = None
    rpc_url: str = ""
    registry_address: str = ""
    adjudicator_address: str = ""
    simulated: bool = True
    note: str = ""

    @classmethod
    def demo(cls, registry_address: str = "", adjudicator_address: str = "") -> "NetworkInfo":
        return cls(
            mode=NetworkMode.DEMO,
            network="demo",
            registry_address=registry_address,
            adjudicator_address=adjudicator_address,
            simulated=True,
            note=(
                "DEMO mode executes the real contract logic in a local development "
                "runtime. There is no GenLayer consensus, no chain, and no LLM call. "
                "Records produced here are simulated and are not historical GenLayer cases."
            ),
        )


# --------------------------------------------------------------------------
# chain primitives
# --------------------------------------------------------------------------
class TxReceipt(BaseModel):
    transaction_reference: str
    status_code: Optional[int] = None
    status: str = "UNKNOWN"           # PROPOSED / ACCEPTED / FINALIZED / REJECTED ...
    execution_result: str = ""
    finality_timestamp: Optional[int] = None
    consensus_data: Dict[str, Any] = Field(default_factory=dict)
    simulated: bool = True

    @property
    def is_final(self) -> bool:
        return self.status_code == TX_STATUS_FINALIZED and self.execution_result == TX_EXECUTION_SUCCESS


class WriteResult(BaseModel):
    transaction_reference: str
    method: str
    receipt: TxReceipt
    result: Any = None
    simulated: bool = True


class FinalityAttestation(BaseModel):
    """The UNVERIFIED RECORD -> FINAL HOLDING boundary."""

    holding_id: str
    tx_status_code: int
    execution_result: str
    finality_timestamp: int
    appeal_outcome: Literal["NONE", "UPHELD", "OVERTURNED", "PENDING"] = "NONE"
    source_tx: str = ""

    @property
    def settles(self) -> bool:
        return (
            self.tx_status_code == TX_STATUS_FINALIZED
            and self.execution_result == TX_EXECUTION_SUCCESS
        )


# --------------------------------------------------------------------------
# domain records (API-facing)
# --------------------------------------------------------------------------
class AuthorityBreakdown(BaseModel):
    component: str
    value_bp: int
    weight_bp: int
    contribution_bp: int
    meaning: str


class Authority(BaseModel):
    score: float
    score_bp: int
    band: Literal["HIGH", "MODERATE", "DEVELOPING"]
    components_bp: Dict[str, int]
    weights_bp: Dict[str, int]
    breakdown: List[AuthorityBreakdown]
    formula: str
    explanation: str


class Finality(BaseModel):
    status: str
    tx_status_code: Optional[int] = None
    execution_result: str = ""
    finality_timestamp: Optional[int] = None
    appeal_status: str = "NONE"
    appeal_outcome: str = "NONE"


class Provenance(BaseModel):
    case_id: str = ""
    source_contract: Optional[str] = None
    source_tx: Optional[str] = None
    holding_hash: Optional[str] = None
    created_at: Optional[int] = None
    schema_version: str = ""
    mode: str = "DEMO"
    simulated: bool = True


class Holding(BaseModel):
    holding_id: str
    display_id: str = ""
    case_id: str = ""
    domain: str = ""
    contract_class: str = ""
    issue: str = ""
    facts_digest: str = ""
    verdict: str = ""
    reason_codes: List[str] = Field(default_factory=list)
    ratio: str = ""
    evidence_hashes: List[str] = Field(default_factory=list)
    panel_size: int = 0
    status: str = "UNVERIFIED"
    finality_timestamp: Optional[int] = None
    created_at: Optional[int] = None
    authority_bp: int = 0
    citation_count: int = 0
    distinguishment_count: int = 0
    parent_holdings: List[str] = Field(default_factory=list)
    contract_address: Optional[str] = None
    transaction_reference: Optional[str] = None
    finality: Finality = Field(default_factory=Finality)
    authority: Optional[Authority] = None
    provenance: Provenance = Field(default_factory=Provenance)
    distinguishment: str = ""
    embedding_vector_ref: str = ""
    simulated: bool = True


class Citation(BaseModel):
    source_holding_id: str
    target_holding_id: str
    relationship: Literal["CITES", "FOLLOWS", "DISTINGUISHES"]
    case_id: str = ""
    created_at: int = 0
    direction: Literal["outgoing", "incoming"] = "outgoing"


class PrecedentHit(BaseModel):
    holding_id: str
    display_id: str = ""
    case_id: str = ""
    domain: str = ""
    issue: str = ""
    ratio: str = ""
    verdict: str = ""
    similarity: float
    similarity_bp: int = 0
    authority_bp: int = 0
    authority: Optional[Authority] = None
    status: str = "FINAL"
    citation_count: int = 0
    distinguishment_count: int = 0
    created_at: Optional[int] = None
    relationship: str = "NONE"


class Case(BaseModel):
    case_id: str
    status: str = "PROPOSED"
    domain: str = ""
    contract_class: str = ""
    facts: List[str] = Field(default_factory=list)
    verdict: str = ""
    ratio: str = ""
    issue: str = ""
    reason_codes: List[str] = Field(default_factory=list)
    precedent_used: List[str] = Field(default_factory=list)
    followed: bool = False
    distinguished: bool = False
    distinguishment_reason: str = ""
    reasoning: str = ""
    panel_size: int = 0
    submitted_at: Optional[int] = None
    holding_id: Optional[str] = None
    transaction_reference: Optional[str] = None
    simulated: bool = True


class RegistryStats(BaseModel):
    sequence: int = 0
    total: int = 0
    final: int = 0
    pending: int = 0
    rejected: int = 0
    unverified: int = 0
    citations: int = 0
    follows: int = 0
    distinguishes: int = 0
    domains: int = 0
    schema_version: str = ""
    embedding_model: str = ""
    embedding_dim: int = 0
    mode: str = "DEMO"
    simulated: bool = True
