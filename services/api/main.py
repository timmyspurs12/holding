"""HOLDING Reporter API.

Reads and writes go through the GenLayer adapter (/services/lib/genlayer).
Nothing here talks to a chain directly, and no raw blockchain object is ever
serialised into a response.

Every response carries the network it came from, so a client can never mistake
a simulated record for a live one.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from ..lib.genlayer.base import AdapterError, ContractRejected, LiveUnavailable
from ..lib.genlayer.client import get_registry, reset
from ..lib.genlayer.config import GenLayerConfig
from ..lib.genlayer.types import Holding, NetworkInfo
from .search import SearchQuery, precedent_view, search
from .security import IdempotencyStore, RateLimiter, client_of, require_admin

logger = logging.getLogger("holding.api")

RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "120") or 120)
CORS_ORIGINS = [origin for origin in (os.getenv("CORS_ORIGINS") or "").split(",") if origin]


def create_app(config: Optional[GenLayerConfig] = None) -> FastAPI:
    config = config or GenLayerConfig.from_env()
    app = FastAPI(
        title="HOLDING Reporter API",
        version="1.0.0",
        description=(
            "Read and write access to the HOLDING precedent registry: a GenLayer "
            "Intelligent Contract that turns finalized adjudications into citable holdings."
        ),
    )
    app.state.config = config
    app.state.limiter = RateLimiter(int(os.getenv("RATE_LIMIT_PER_MINUTE", RATE_LIMIT_PER_MINUTE) or RATE_LIMIT_PER_MINUTE))
    app.state.idempotency = IdempotencyStore()
    app.state.started_at = int(time.time())

    if CORS_ORIGINS:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=CORS_ORIGINS,
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type", "X-Admin-Token", "Idempotency-Key"],
        )

    from .routers.admin import router as admin_router
    from .routers.demo import router as demo_router

    app.include_router(admin_router)
    app.include_router(demo_router)

    @app.on_event("startup")
    def seed_demo_corpus() -> None:
        """In DEMO mode, populate the registry with the canonical loop.

        Disabled with HOLDING_DEMO_SEED=false. Everything produced here is
        simulated and labelled as such by the network block on every response.
        """
        if config.mode.value != "DEMO":
            return
        if os.getenv("HOLDING_DEMO_SEED", "true").lower() in ("0", "false", "no"):
            return
        from .routers.demo import SEED_CASES, run_case

        shim = type("_StartupRequest", (), {})()
        shim.app = type("_App", (), {"state": app.state})()

        for case in SEED_CASES:
            try:
                run_case(shim, case["case_id"], case["facts"], settle=True)
            except Exception as error:  # pragma: no cover - startup best effort
                logger.warning("demo seed failed for %s: %s", case["case_id"], error)

    # -- dependencies -------------------------------------------------
    def registry():
        try:
            return get_registry(app.state.config)
        except LiveUnavailable as error:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error
        except ValueError as error:  # misconfigured live network
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from error

    def network() -> NetworkInfo:
        return app.state.config.info()

    def envelope(items: List[Any], *, total: int, limit: int, offset: int, extra: Optional[Dict[str, Any]] = None):
        payload: Dict[str, Any] = {
            "network": network().model_dump(),
            "total": total,
            "limit": limit,
            "offset": offset,
            "items": items,
        }
        if extra:
            payload.update(extra)
        return payload

    # -- middleware ---------------------------------------------------
    @app.middleware("http")
    async def rate_limit(request: Request, call_next):
        if not request.url.path.startswith("/health"):
            try:
                app.state.limiter.check(client_of(request))
            except HTTPException as error:
                return JSONResponse(
                    status_code=error.status_code,
                    content={"detail": error.detail},
                    headers=error.headers,
                )
        return await call_next(request)

    # -- error translation --------------------------------------------
    @app.exception_handler(RequestValidationError)
    async def request_invalid(request: Request, error: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "detail": "invalid request payload",
                "type": "request_invalid",
                "errors": jsonable_encoder(error.errors()),
            },
        )

    @app.exception_handler(ContractRejected)
    async def contract_rejected(request: Request, error: ContractRejected):
        return JSONResponse(status_code=422, content={"detail": str(error), "type": "contract_rejected"})

    @app.exception_handler(AdapterError)
    async def adapter_error(request: Request, error: AdapterError):
        logger.warning("adapter error: %s", error)
        return JSONResponse(status_code=503, content={"detail": str(error), "type": "adapter_unavailable"})

    # -- meta ----------------------------------------------------------
    @app.get("/health", tags=["meta"], summary="Service, network and registry health")
    def health():
        reg = get_registry(app.state.config)
        reachable = True
        stats: Dict[str, Any] = {}
        try:
            stats = reg.stats().model_dump()
        except Exception as error:  # pragma: no cover - depends on the network
            reachable = False
            logger.warning("registry unreachable: %s", error)
        return {
            "status": "ok" if reachable else "degraded",
            "service": "holding-reporter",
            "version": "1.0.0",
            "uptime_seconds": int(time.time()) - app.state.started_at,
            "network": network().model_dump(),
            "registry": {"address": app.state.config.registry_address, "reachable": reachable, "stats": stats},
        }

    @app.get("/stats", tags=["meta"], summary="Registry totals and authority distribution")
    def stats(reg=Depends(registry)):
        payload = reg.stats().model_dump()
        payload["network"] = network().model_dump()
        holdings = reg.list_holdings(limit=10_000)
        bands = {"HIGH": 0, "MODERATE": 0, "DEVELOPING": 0}
        for holding in holdings:
            if holding.authority:
                bands[holding.authority.band] = bands.get(holding.authority.band, 0) + 1
        payload["authority_bands"] = bands
        return payload

    @app.get("/domains", tags=["meta"], summary="Domains present in the registry")
    def domains(reg=Depends(registry)):
        holdings = reg.list_holdings(limit=10_000)
        grouped: Dict[str, Dict[str, Any]] = {}
        for holding in holdings:
            entry = grouped.setdefault(
                holding.domain or "unknown",
                {"domain": holding.domain or "unknown", "holdings": 0, "final": 0, "follows": 0, "distinguishes": 0},
            )
            entry["holdings"] += 1
            if holding.status == "FINAL":
                entry["final"] += 1
            entry["follows"] += int(holding.citation_count)
            entry["distinguishes"] += int(holding.distinguishment_count)
        items = sorted(grouped.values(), key=lambda item: (-item["holdings"], item["domain"]))
        return envelope(items, total=len(items), limit=len(items), offset=0)

    # -- holdings -------------------------------------------------------
    @app.get("/holdings", tags=["holdings"], summary="List and filter holdings")
    def list_holdings(
        domain: str = "",
        contract_class: str = "",
        status_filter: str = Query(default="", alias="status"),
        verdict: str = "",
        appeal_outcome: str = "",
        min_authority: Optional[float] = None,
        max_authority: Optional[float] = None,
        since: Optional[int] = None,
        until: Optional[int] = None,
        limit: int = 50,
        offset: int = 0,
        sort: str = "authority",
        reg=Depends(registry),
    ):
        query = SearchQuery(
            domain=domain,
            contract_class=contract_class,
            status=status_filter,
            verdict=verdict,
            appeal_outcome=appeal_outcome,
            min_authority=min_authority,
            max_authority=max_authority,
            since=since,
            until=until,
            sort=sort,
        )
        limit = max(1, min(int(limit), 200))
        offset = max(0, int(offset))
        matches = search(reg, query)
        # no query text -> catalogue ordering with pagination applied here
        if not query.q:
            return envelope(
                matches[offset : offset + limit], total=len(matches), limit=limit, offset=offset
            )
        return envelope(matches, total=len(matches), limit=len(matches), offset=0)

    @app.get("/holdings/search", tags=["holdings"], summary="Semantic search with metadata filters")
    def search_holdings(
        q: str = "",
        domain: str = "",
        contract_class: str = "",
        status_filter: str = Query(default="", alias="status"),
        verdict: str = "",
        appeal_outcome: str = "",
        min_authority: Optional[float] = None,
        since: Optional[int] = None,
        until: Optional[int] = None,
        k: int = 10,
        reg=Depends(registry),
    ):
        query = SearchQuery(
            q=q,
            domain=domain,
            contract_class=contract_class,
            status=status_filter,
            verdict=verdict,
            appeal_outcome=appeal_outcome,
            min_authority=min_authority,
            since=since,
            until=until,
            k=k,
        )
        items = search(reg, query)
        return envelope(items, total=len(items), limit=query.k, offset=0, extra={"query": query.q})

    def _holding_or_404(reg, holding_id: str) -> Holding:
        holding = reg.get_holding(holding_id)
        if holding is None:
            raise HTTPException(status_code=404, detail=f"unknown holding {holding_id}")
        return holding

    @app.get("/holdings/{holding_id}", tags=["holdings"], summary="A single holding with authority and provenance")
    def get_holding(holding_id: str, reg=Depends(registry)):
        return _holding_or_404(reg, holding_id).model_dump()

    @app.get("/holdings/{holding_id}/citations", tags=["holdings"], summary="Citation graph edges")
    def get_citations(holding_id: str, relationship: str = "", reg=Depends(registry)):
        _holding_or_404(reg, holding_id)
        items = [edge.model_dump() for edge in reg.get_citations(holding_id)]
        if relationship:
            wanted = relationship.upper()
            items = [edge for edge in items if edge["relationship"] == wanted]
        return envelope(items, total=len(items), limit=len(items), offset=0)

    @app.get("/holdings/{holding_id}/precedent", tags=["holdings"], summary="The precedent a panel would be shown")
    def get_precedent(holding_id: str, k: int = 3, reg=Depends(registry)):
        holding = _holding_or_404(reg, holding_id)
        hits = precedent_view(reg, holding, max(1, min(int(k), 10)))
        return envelope(
            [hit.model_dump() for hit in hits],
            total=len(hits),
            limit=len(hits),
            offset=0,
            extra={"for_holding": holding.holding_id, "retrieval": "contract VecDB, pinned embedding model"},
        )

    @app.get("/holdings/{holding_id}/distinguishments", tags=["holdings"], summary="Holdings that departed from this one")
    def get_distinguishments(holding_id: str, reg=Depends(registry)):
        _holding_or_404(reg, holding_id)
        items = reg.get_distinguishments(holding_id)
        return envelope(items, total=len(items), limit=len(items), offset=0)

    # -- cases ----------------------------------------------------------
    @app.get("/cases", tags=["cases"], summary="Adjudicated cases (the adjudicator contract)")
    def list_cases(reg=Depends(registry)):
        ids = reg.list_cases()
        items = []
        for case_id in ids:
            case = reg.get_case(case_id)
            if case is not None:
                items.append(case.model_dump())
        return envelope(items, total=len(items), limit=len(items), offset=0)

    @app.get("/cases/{case_id}", tags=["cases"], summary="A case with the holding it produced")
    def get_case(case_id: str, reg=Depends(registry)):
        case = reg.get_case(case_id)
        if case is None:
            raise HTTPException(status_code=404, detail=f"unknown case {case_id}")
        payload = case.model_dump()
        if case.holding_id:
            holding = reg.get_holding(case.holding_id)
            payload["holding"] = holding.model_dump() if holding else None
        return payload

    @app.post("/admin/reload", tags=["admin"], summary="Drop cached chain clients")
    def reload(x_admin_token: Optional[str] = Header(default=None)):
        require_admin(config, x_admin_token)
        reset()
        return {"reloaded": True, "network": network().model_dump()}

    return app


app = create_app()
