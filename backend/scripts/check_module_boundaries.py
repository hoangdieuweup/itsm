#!/usr/bin/env python3
"""Lint: enforce cross-module imports go through `public.py` only.

Rule
----
A file inside ``app/modules/<A>/`` may freely import from ``app.modules.<A>.*``
(same module – no restriction).  But if it imports from ``app.modules.<B>``
where ``B ≠ A``, the import **must** target ``app.modules.<B>.public``.

Any other cross-module import path is flagged as a violation.

Usage
-----
    python scripts/check_module_boundaries.py          # from backend/
    python scripts/check_module_boundaries.py --strict # exit 1 on violations
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path
from dataclasses import dataclass

# ── Configuration ──────────────────────────────────────────────────────────

MODULES_ROOT = Path(__file__).resolve().parent.parent / "app" / "modules"
MODULE_IMPORT_PREFIX = "app.modules."


# ── Data ───────────────────────────────────────────────────────────────────

@dataclass
class Violation:
    file: Path
    line: int
    source_module: str
    target_module: str
    import_path: str

    def __str__(self) -> str:
        rel = self.file.relative_to(MODULES_ROOT.parent.parent)
        return (
            f"  {rel}:{self.line}  "
            f"module '{self.source_module}' imports '{self.import_path}' "
            f"— should use 'app.modules.{self.target_module}.public'"
        )


# ── Helpers ────────────────────────────────────────────────────────────────

def _owning_module(py_file: Path) -> str | None:
    """Return the module name that *owns* ``py_file``, or None."""
    try:
        rel = py_file.relative_to(MODULES_ROOT)
    except ValueError:
        return None
    parts = rel.parts  # e.g. ("auth", "services", "authenticate.py")
    return parts[0] if parts else None


def _extract_imports(source: str) -> list[tuple[int, str]]:
    """Return ``(lineno, dotted_path)`` for every ``from X import …`` / ``import X``."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    results: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            results.append((node.lineno, node.module))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                results.append((node.lineno, alias.name))
    return results


def _target_module(import_path: str) -> str | None:
    """If ``import_path`` starts with ``app.modules.<name>``, return ``<name>``."""
    if not import_path.startswith(MODULE_IMPORT_PREFIX):
        return None
    rest = import_path[len(MODULE_IMPORT_PREFIX):]
    parts = rest.split(".")
    return parts[0] if parts else None


def _is_public_import(import_path: str, target_mod: str) -> bool:
    """True when the import resolves to ``app.modules.<target>.public`` or ``app.modules.<target>.constants``."""
    return import_path in (
        f"{MODULE_IMPORT_PREFIX}{target_mod}.public",
        f"{MODULE_IMPORT_PREFIX}{target_mod}.constants",
    )


# ── Core check ─────────────────────────────────────────────────────────────

def check_file(py_file: Path) -> list[Violation]:
    source_mod = _owning_module(py_file)
    if source_mod is None:
        return []

    source = py_file.read_text(encoding="utf-8")
    violations: list[Violation] = []

    for lineno, imp in _extract_imports(source):
        target_mod = _target_module(imp)
        if target_mod is None:
            continue  # not a module-level import
        if target_mod == source_mod:
            continue  # same module → always OK
        if _is_public_import(imp, target_mod):
            continue  # goes through public.py → OK

        violations.append(
            Violation(
                file=py_file,
                line=lineno,
                source_module=source_mod,
                target_module=target_mod,
                import_path=imp,
            )
        )
    return violations


def check_all() -> list[Violation]:
    violations: list[Violation] = []
    for py_file in sorted(MODULES_ROOT.rglob("*.py")):
        violations.extend(check_file(py_file))
    return violations


# ── CLI ────────────────────────────────────────────────────────────────────

_RED = "\033[91m"
_GREEN = "\033[92m"
_YELLOW = "\033[93m"
_BOLD = "\033[1m"
_RESET = "\033[0m"


def main() -> None:
    parser = argparse.ArgumentParser(description="Check cross-module import boundaries")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with code 1 if any violations are found",
    )
    args = parser.parse_args()

    violations = check_all()

    if not violations:
        print(f"{_GREEN}✓ No cross-module boundary violations found.{_RESET}")
        return

    # Group by source file
    by_file: dict[Path, list[Violation]] = {}
    for v in violations:
        by_file.setdefault(v.file, []).append(v)

    print(f"\n{_RED}{_BOLD}✗ Found {len(violations)} cross-module boundary violation(s):{_RESET}\n")

    for file, file_violations in by_file.items():
        rel = file.relative_to(MODULES_ROOT.parent.parent)
        print(f"  {_BOLD}{rel}{_RESET}")
        for v in file_violations:
            print(
                f"    {_YELLOW}L{v.line}{_RESET}  "
                f"imports {_RED}{v.import_path}{_RESET}  "
                f"→  should be {_GREEN}app.modules.{v.target_module}.public{_RESET}"
            )
        print()

    print(
        f"  {_BOLD}Rule:{_RESET} Cross-module imports must go through "
        f"'app.modules.<name>.public', not internal submodules.\n"
    )

    if args.strict:
        sys.exit(1)


if __name__ == "__main__":
    main()
