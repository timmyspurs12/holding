"""HOLDING indexer — a read-side convenience layer, never the source of truth.

What it does
------------
Watches the registry for settled transactions, then mirrors holdings, cases,
citations and provenance into a local SQLite store so the Reporter can serve
fast searches, facets and "where did this holding come from?" lookups.

What it never does
------------------
It never writes to the contract, never decides status, and never invents
records. Every row it stores is copied from the contract and keeps the holding
hash it was derived from; if the contract and the local store disagree, the
contract wins and the row is refreshed on the next poll.

Run:  python -m services.indexer.indexer --once
      python -m services.indexer.indexer --interval 30
"""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from shared.holding_core import schema as holding_schema

from ..lib.genlayer.base import AdapterError, ContractRejected
from ..lib.genlayer.client import get_registry
from ..lib.genlayer.config import GenLayerConfig
from ..lib.genlayer.types import Holding

logger = logging.getLogger("holding.indexer")

DEFAULT_DB = Path("data/indexer.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS holdings (
    holding_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    domain TEXT NOT NULL,
    contract_class TEXT,
    issue TEXT,
    facts_digest TEXT,
    verdict TEXT,
    ratio TEXT,
    status TEXT NOT NULL,
    authority_bp INTEGER DEFAULT 0,
    citation_count INTEGER DEFAULT 0,
    distinguishment_count INTEGER DEFAULT 0,
    finality_timestamp INTEGER,
    created_at INTEGER,
    source_contract TEXT,
    source_tx TEXT,
    holding_hash TEXT,
    reason_codes TEXT,
    evidence_hashes TEXT,
    distinguishment TEXT,
    simulated INTEGER DEFAULT 1,
    updated_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_holdings_domain ON holdings(domain);
CREATE INDEX IF NOT EXISTS idx_holdings_status ON holdings(status);
CREATE INDEX IF NOT EXISTS idx_holdings_case ON holdings(case_id);

CREATE TABLE IF NOT EXISTS citations (
    source_holding_id TEXT NOT NULL,
    target_holding_id TEXT NOT NULL,
    relationship TEXT NOT NULL,
    case_id TEXT,
    created_at INTEGER,
    PRIMARY KEY (source_holding_id, target_holding_id, relationship)
);
CREATE INDEX IF NOT EXISTS idx_citations_target ON citations(target_holding_id);

CREATE TABLE IF NOT EXISTS cases (
    case_id TEXT PRIMARY KEY,
    status TEXT,
    domain TEXT,
    verdict TEXT,
    followed INTEGER DEFAULT 0,
    distinguished INTEGER DEFAULT 0,
    precedent_used TEXT,
    distinguishment_reason TEXT,
    holding_id TEXT,
    simulated INTEGER DEFAULT 1,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at INTEGER NOT NULL,
    finished_at INTEGER,
    mode TEXT,
    holdings INTEGER DEFAULT 0,
    citations INTEGER DEFAULT 0,
    cases INTEGER DEFAULT 0,
    note TEXT
);
"""


@dataclass
class IndexResult:
    holdings: int = 0
    citations: int = 0
    cases: int = 0
    new_holdings: List[str] = None  # type: ignore[assignment]
    newly_final: List[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.new_holdings = self.new_holdings or []
        self.newly_final = self.newly_final or []


class Indexer:
    def __init__(self, config: Optional[GenLayerConfig] = None, db_path: Path = DEFAULT_DB) -> None:
        self.config = config or GenLayerConfig.from_env()
        self.registry = get_registry(self.config)
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.db_path)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(SCHEMA)
        self.connection.commit()

    # -- storage ------------------------------------------------------
    def _existing(self, holding_id: str) -> Optional[sqlite3.Row]:
        cursor = self.connection.execute("SELECT * FROM holdings WHERE holding_id = ?", (holding_id,))
        return cursor.fetchone()

    @staticmethod
    def _hash_of(holding: Holding) -> str:
        return holding_schema.holding_hash(
            {
                "case_id": holding.case_id,
                "source_contract": holding.provenance.source_contract or "",
                "source_tx": holding.provenance.source_tx or "",
                "domain": holding.domain,
                "contract_class": holding.contract_class,
                "issue": holding.issue,
                "facts_digest": holding.facts_digest,
                "verdict": holding.verdict,
                "ratio": holding.ratio,
                "reason_codes": holding.reason_codes,
                "evidence_hashes": holding.evidence_hashes,
                "panel_size": holding.panel_size,
            }
        )

    def _upsert_holding(self, holding: Holding, now: int) -> bool:
        """Return True when this is a record the indexer had not seen."""
        existing = self._existing(holding.holding_id)
        digest = self._hash_of(holding)
        simulated = 1 if holding.provenance.simulated else 0
        values = (
            holding.holding_id,
            holding.case_id,
            holding.domain,
            holding.contract_class,
            holding.issue,
            holding.facts_digest,
            holding.verdict,
            holding.ratio,
            holding.status,
            int(holding.authority_bp),
            int(holding.citation_count),
            int(holding.distinguishment_count),
            holding.finality_timestamp,
            holding.created_at,
            holding.provenance.source_contract or "",
            holding.provenance.source_tx or "",
            digest,
            json.dumps(holding.reason_codes),
            json.dumps(holding.evidence_hashes),
            holding.distinguishment,
            simulated,
            now,
        )
        self.connection.execute(
            """INSERT INTO holdings VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(holding_id) DO UPDATE SET
                 case_id=excluded.case_id, domain=excluded.domain,
                 contract_class=excluded.contract_class, issue=excluded.issue,
                 facts_digest=excluded.facts_digest, verdict=excluded.verdict,
                 ratio=excluded.ratio, status=excluded.status,
                 authority_bp=excluded.authority_bp,
                 citation_count=excluded.citation_count,
                 distinguishment_count=excluded.distinguishment_count,
                 finality_timestamp=excluded.finality_timestamp,
                 created_at=excluded.created_at,
                 source_contract=excluded.source_contract, source_tx=excluded.source_tx,
                 holding_hash=excluded.holding_hash, reason_codes=excluded.reason_codes,
                 evidence_hashes=excluded.evidence_hashes,
                 distinguishment=excluded.distinguishment,
                 simulated=excluded.simulated, updated_at=excluded.updated_at""",
            values,
        )
        return existing is None

    def _upsert_citation(self, citation: Dict[str, Any]) -> None:
        self.connection.execute(
            """INSERT INTO citations VALUES (?,?,?,?,?)
               ON CONFLICT(source_holding_id, target_holding_id, relationship)
               DO UPDATE SET case_id=excluded.case_id, created_at=excluded.created_at""",
            (
                citation["source_holding_id"],
                citation["target_holding_id"],
                citation["relationship"],
                citation.get("case_id", ""),
                int(citation.get("created_at", 0) or 0),
            ),
        )

    def _upsert_case(self, case_id: str, case: Any, now: int) -> None:
        self.connection.execute(
            """INSERT INTO cases VALUES (?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(case_id) DO UPDATE SET
                 status=excluded.status, domain=excluded.domain, verdict=excluded.verdict,
                 followed=excluded.followed, distinguished=excluded.distinguished,
                 precedent_used=excluded.precedent_used,
                 distinguishment_reason=excluded.distinguishment_reason,
                 holding_id=excluded.holding_id, simulated=excluded.simulated,
                 updated_at=excluded.updated_at""",
            (
                case_id,
                case.status,
                case.domain,
                case.verdict,
                1 if case.followed else 0,
                1 if case.distinguished else 0,
                json.dumps(case.precedent_used),
                case.distinguishment_reason,
                case.holding_id or "",
                1 if case.simulated else 0,
                now,
            ),
        )

    # -- the poll -----------------------------------------------------
    def run_once(self) -> IndexResult:
        now = int(time.time())
        result = IndexResult()
        try:
            holdings = self.registry.list_holdings(limit=10_000)
        except (AdapterError, ContractRejected) as error:
            logger.warning("registry read failed, keeping the last known index: %s", error)
            return result

        seen_edges = set()
        for holding in holdings:
            previous = self._existing(holding.holding_id)
            previous_status = previous["status"] if previous is not None else None

            is_new = self._upsert_holding(holding, now)
            if is_new:
                result.new_holdings.append(holding.holding_id)
            if holding.status == "FINAL" and previous_status != "FINAL":
                result.newly_final.append(holding.holding_id)
            result.holdings += 1

            for citation in self.registry.get_citations(holding.holding_id):
                edge = citation.model_dump()
                key = (edge["source_holding_id"], edge["target_holding_id"], edge["relationship"])
                if key in seen_edges:
                    continue
                seen_edges.add(key)
                self._upsert_citation(edge)
                result.citations += 1

        for case_id in self.registry.list_cases():
            case = self.registry.get_case(case_id)
            if case is not None:
                self._upsert_case(case_id, case, now)
                result.cases += 1

        self.connection.execute(
            "INSERT INTO runs (started_at, finished_at, mode, holdings, citations, cases, note) VALUES (?,?,?,?,?,?,?)",
            (now, int(time.time()), self.config.mode.value, result.holdings, result.citations, result.cases, ""),
        )
        self.connection.commit()
        logger.info(
            "indexed %s holdings, %s citation rows, %s cases (mode=%s)",
            result.holdings,
            result.citations,
            result.cases,
            self.config.mode.value,
        )
        return result

    def run(self, interval: int = 30, once: bool = False) -> None:
        while True:
            try:
                self.run_once()
            except Exception as error:  # keep the loop alive, log loudly
                logger.exception("indexer iteration failed: %s", error)
            if once:
                return
            time.sleep(max(1, int(interval)))

    # -- read helpers (used by the Reporter, always contract-verifiable) --
    def search_text(self, query: str, domain: str = "", limit: int = 20) -> List[Dict[str, Any]]:
        """Full-text-ish fallback over the mirrored corpus. Contract retrieval is
        still authoritative; this only helps the Reporter answer quickly."""
        like = f"%{query.lower()}%"
        sql = """SELECT * FROM holdings
                 WHERE (lower(issue) LIKE ? OR lower(ratio) LIKE ? OR lower(facts_digest) LIKE ?
                        OR lower(domain) LIKE ? OR lower(contract_class) LIKE ? OR lower(verdict) LIKE ?)"""
        params: List[Any] = [like, like, like, like, like, like]
        if domain:
            sql += " AND domain = ?"
            params.append(domain)
        sql += " ORDER BY authority_bp DESC, holding_id ASC LIMIT ?"
        params.append(int(limit))
        cursor = self.connection.execute(sql, params)
        return [dict(row) for row in cursor.fetchall()]

    def provenance(self, holding_id: str) -> Optional[Dict[str, Any]]:
        cursor = self.connection.execute("SELECT * FROM holdings WHERE holding_id = ?", (holding_id,))
        row = cursor.fetchone()
        if row is None:
            return None
        record = dict(row)
        return {
            "holding_id": record["holding_id"],
            "case_id": record["case_id"],
            "source_contract": record["source_contract"],
            "source_tx": record["source_tx"],
            "holding_hash": record["holding_hash"],
            "finality_timestamp": record["finality_timestamp"],
            "status": record["status"],
            "evidence_hashes": json.loads(record["evidence_hashes"] or "[]"),
            "simulated": bool(record["simulated"]),
            "note": "mirrored from the registry contract — the contract is canonical",
        }

    def close(self) -> None:
        self.connection.close()


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="HOLDING indexer")
    parser.add_argument("--once", action="store_true", help="run a single pass and exit")
    parser.add_argument("--interval", type=int, default=30, help="seconds between passes")
    parser.add_argument("--db", default=str(DEFAULT_DB), help="sqlite path")
    args = parser.parse_args(list(argv) if argv is not None else None)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    indexer = Indexer(db_path=Path(args.db))
    indexer.run(interval=args.interval, once=args.once)
    indexer.close()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
