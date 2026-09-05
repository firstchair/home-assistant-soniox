"""Make ``custom_components.soniox`` importable without Home Assistant installed.

``helpers.py`` and ``api.py`` deliberately avoid HA imports; the package
``__init__`` does import HA, so we stub the package module and import the
submodules directly.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "custom_components" / "soniox"


def _load(name: str) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(f"custom_components.soniox.{name}", ROOT / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load_modules() -> dict[str, types.ModuleType]:
    """Stub the package and load the HA-free submodules; idempotent."""
    if "custom_components.soniox" not in sys.modules:
        pkg = types.ModuleType("custom_components.soniox")
        pkg.__path__ = [str(ROOT)]  # type: ignore[attr-defined]
        sys.modules.setdefault("custom_components", types.ModuleType("custom_components"))
        sys.modules["custom_components.soniox"] = pkg
    for name in ("const", "helpers", "api"):
        if f"custom_components.soniox.{name}" not in sys.modules:
            _load(name)
    return {name: sys.modules[f"custom_components.soniox.{name}"] for name in ("const", "helpers", "api")}


load_modules()
