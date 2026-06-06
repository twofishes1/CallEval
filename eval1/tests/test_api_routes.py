"""Eval1 API is self-contained (no eval_system import)."""

from __future__ import annotations

import importlib
from pathlib import Path


def test_eval1_routes_no_eval_system_dependency():
    routes = importlib.import_module("eval1.api.read_routes")
    src = Path(routes.__file__).read_text(encoding="utf-8")
    assert "eval_system" not in src
    assert "def datasets" in src
    assert "def layer2_dialogues" in src


def test_eval1_main_entry_docstring():
    main = importlib.import_module("eval1.main")
    assert "eval_system" not in (main.__doc__ or "").lower() or "no eval_system" in (main.__doc__ or "").lower()
