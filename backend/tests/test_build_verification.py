"""
Smoke tests to verify backend build integrity.

These tests intentionally avoid starting external dependencies (DB, workers).
They focus on syntax/import correctness and route registration.
"""

from __future__ import annotations

import importlib
from pathlib import Path


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_backend_python_sources_compile() -> None:
    backend_root = _backend_root()
    for py_file in backend_root.rglob("*.py"):
        if "tests" in py_file.parts:
            continue
        source = py_file.read_text(encoding="utf-8")
        compile(source, str(py_file), "exec")


def test_main_module_imports_and_exposes_app() -> None:
    module = importlib.import_module("backend.main")
    assert hasattr(module, "app")
    assert module.app.title == "AICT Backend"


def test_core_routes_are_registered() -> None:
    app = importlib.import_module("backend.main").app
    paths = {route.path for route in app.routes}
    assert "/api/v1/health" in paths
    assert "/api/v1/health/workers" in paths
    assert "/internal/agent/health" in paths
    assert "/ws" in paths
