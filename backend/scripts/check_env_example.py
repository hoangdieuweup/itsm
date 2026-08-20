#!/usr/bin/env python3
"""Assert every Settings field across app/**/config.py has a matching key in
.env.example, per fastapi-modular-scaffold/references/deployment.md ("Every
variable the app reads, with safe/placeholder defaults.").

Run manually (or as part of the pre-handover checklist) after adding/renaming
a Settings field:

    uv run python scripts/check_env_example.py

Exits non-zero and prints the missing env var names if any are undocumented.
This intentionally only checks presence of the *key*, never its value, so it
never needs to know or assert a real secret.
"""

from __future__ import annotations

import importlib
import inspect
import sys
from pathlib import Path

from pydantic_settings import BaseSettings

BACKEND_ROOT = Path(__file__).resolve().parent.parent
ENV_EXAMPLE_PATH = BACKEND_ROOT / ".env.example"


def _discover_config_modules() -> list[str]:
    """Dotted module paths for every app/**/config.py file."""
    paths = sorted((BACKEND_ROOT / "app").rglob("config.py"))
    modules = []
    for path in paths:
        relative = path.relative_to(BACKEND_ROOT).with_suffix("")
        modules.append(".".join(relative.parts))
    return modules


def _settings_env_vars(module_name: str) -> set[str]:
    """Every fully-prefixed env var name declared by BaseSettings subclasses
    defined directly in this module (not imported from elsewhere)."""
    module = importlib.import_module(module_name)
    env_vars: set[str] = set()
    for _, obj in inspect.getmembers(module, inspect.isclass):
        if obj.__module__ != module_name:
            continue
        if not (issubclass(obj, BaseSettings) and obj is not BaseSettings):
            continue
        prefix = obj.model_config.get("env_prefix", "")
        for field_name in obj.model_fields:
            env_vars.add(f"{prefix}{field_name}")
    return env_vars


def _documented_env_vars() -> set[str]:
    documented: set[str] = set()
    for line in ENV_EXAMPLE_PATH.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        documented.add(stripped.split("=", 1)[0])
    return documented


def main() -> int:
    documented = _documented_env_vars()
    missing: dict[str, set[str]] = {}

    for module_name in _discover_config_modules():
        required = _settings_env_vars(module_name)
        gap = required - documented
        if gap:
            missing[module_name] = gap

    if not missing:
        print(f"OK: every Settings field is documented in {ENV_EXAMPLE_PATH.name}")
        return 0

    print(f"FAIL: Settings fields missing from {ENV_EXAMPLE_PATH.name}:")
    for module_name, env_vars in sorted(missing.items()):
        for env_var in sorted(env_vars):
            print(f"  {env_var}  (from {module_name})")
    return 1


if __name__ == "__main__":
    sys.exit(main())
