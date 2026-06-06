"""Eval1 FastAPI application — self-contained API entry (no eval_system dependency)."""

from __future__ import annotations

import asyncio
import logging
import os
import pathlib
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

_EVAL1_ROOT = pathlib.Path(__file__).resolve().parent
_DIST = _EVAL1_ROOT.parent / "frontend" / "dist"

_api_loaded = False
_spa_fallback_registered = False


def _configure_logging() -> None:
    level_name = os.environ.get("EVAL_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    pkg = logging.getLogger("eval1")
    pkg.setLevel(level)
    if not pkg.handlers:
        handler = logging.StreamHandler()
        handler.setLevel(level)
        handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
                datefmt="%H:%M:%S",
            )
        )
        pkg.addHandler(handler)


def _register_spa_fallback() -> None:
    """Register SPA catch-all AFTER /api routes so API is not shadowed."""
    global _spa_fallback_registered
    if _spa_fallback_registered or not _DIST.exists():
        return

    @app.get("/{full_path:path}")
    def serve_spa(full_path: str):
        candidate = _DIST / full_path
        if candidate.exists() and candidate.is_file():
            return FileResponse(str(candidate))
        return FileResponse(str(_DIST / "index.html"))

    _spa_fallback_registered = True


def _ensure_api_routes() -> None:
    """Load heavy API deps (langgraph, etc.) on first use, not at process start."""
    global _api_loaded
    if _api_loaded:
        return
    from eval1.api.routes import router as eval1_router

    app.include_router(eval1_router, prefix="/api/eval1")
    _register_spa_fallback()
    _api_loaded = True
    logging.getLogger("eval1.main").info("Eval1 API routes loaded — /api/eval1")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _configure_logging()
    for sub in ("outputs", "data/uploads"):
        (_EVAL1_ROOT / sub).mkdir(parents=True, exist_ok=True)
    logging.getLogger("eval1.main").info("Loading Eval1 API routes (sync)…")
    await asyncio.to_thread(_ensure_api_routes)
    logging.getLogger("eval1.main").info("Eval1 API ready")
    yield


app = FastAPI(
    title="Eval1 Multi-turn Evaluation",
    description="复杂指令多轮对话评测：Layer1 解析 → Layer2 仿真 → Layer3 评分",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _lazy_api_middleware(request, call_next):
    path = request.url.path
    if path.startswith("/api/eval1") and not _api_loaded:
        await asyncio.to_thread(_ensure_api_routes)
    return await call_next(request)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/healthz")
def root_healthz():
    return {"ok": True}


@app.get("/api/eval1/deploy-status")
def deploy_status():
    """Lightweight diagnostics — always available, no lazy import."""
    out_dir = _EVAL1_ROOT / "outputs"
    data_xlsx = _EVAL1_ROOT / "data" / "data.xlsx"
    return {
        "api_loaded": _api_loaded,
        "data_xlsx_exists": data_xlsx.is_file(),
        "report_files": sorted(p.name for p in out_dir.glob("eval1_reports_*.json")),
        "frontend_dist": _DIST.is_dir(),
    }


@app.get("/")
def root():
    """Respond on / even when frontend dist is missing (Railway healthcheck)."""
    index = _DIST / "index.html"
    if index.is_file():
        return FileResponse(str(index))
    return {"status": "ok", "service": "Eval1", "api": "/api/eval1", "docs": "/docs"}


# Static assets only — SPA catch-all is registered after /api in _register_spa_fallback()
if _DIST.exists():
    _assets = _DIST / "assets"
    if _assets.exists():
        app.mount("/assets", StaticFiles(directory=str(_assets)), name="assets")
