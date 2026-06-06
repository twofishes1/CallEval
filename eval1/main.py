"""Eval1 FastAPI application — self-contained API entry (no eval_system dependency)."""

from __future__ import annotations

import logging
import os
import pathlib

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from eval1.api.routes import router as eval1_router

app = FastAPI(
    title="Eval1 Multi-turn Evaluation",
    description="复杂指令多轮对话评测：Layer1 解析 → Layer2 仿真 → Layer3 评分",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(eval1_router, prefix="/api/eval1")


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


@app.on_event("startup")
def on_startup() -> None:
    _configure_logging()
    logging.getLogger("eval1.main").info("Eval1 API 已启动 — 前缀 /api/eval1")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/healthz")
def root_healthz():
    return {"ok": True}


# Serve frontend static files (must be registered after all API routes)
_DIST = pathlib.Path(__file__).parent.parent / "frontend" / "dist"
if _DIST.exists():
    _assets = _DIST / "assets"
    if _assets.exists():
        app.mount("/assets", StaticFiles(directory=str(_assets)), name="assets")

    @app.get("/")
    def serve_index():
        return FileResponse(str(_DIST / "index.html"))

    @app.get("/{full_path:path}")
    def serve_spa(full_path: str):
        candidate = _DIST / full_path
        if candidate.exists() and candidate.is_file():
            return FileResponse(str(candidate))
        return FileResponse(str(_DIST / "index.html"))
