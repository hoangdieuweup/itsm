"""
Generate a modular FastAPI project where every module owns its own constants,
config, exceptions and utils, and every integration is a module in its own right.

Usage:
    python scaffold.py --name shop --output ./shop \
        --modules identity,billing --integrations cache,queue
    python scaffold.py --add-module catalog --output ./shop
    python scaffold.py --add-integration storage --output ./shop
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from templates import domain, integration, project, root
from templates import seeds as seed_templates
from templates import tests as test_templates

INTEGRATIONS = tuple(integration.RENDERERS)


def write(base: Path, rel: str, content: str, executable: bool = False) -> None:
    """Write one file, creating parent directories as needed."""
    path = base / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.lstrip("\n"), encoding="utf-8")
    if executable:
        path.chmod(0o755)


def build_root(base: Path, name: str, modules: list[str], integrations: list[str]) -> None:
    """Create the application root, which holds mechanism only."""
    write(base, "app/__init__.py", "")
    write(base, "app/main.py", root.main(modules))
    write(base, "app/config.py", root.config(name))
    write(base, "app/constants.py", root.constants())
    write(base, "app/lifespan.py", root.lifespan(integrations))

    # core/ — shared mechanism, no business concept
    write(base, "app/core/__init__.py", "")
    write(base, "app/core/database.py", root.database())
    write(base, "app/core/exceptions.py", root.exceptions())
    write(base, "app/core/models.py", root.models())
    write(base, "app/core/pagination.py", root.pagination())
    write(base, "app/core/events.py", root.events())
    write(base, "app/core/middleware.py", root.middleware())
    write(base, "app/core/logging_config.py", root.logging_config("tracing" in integrations))
    write(base, "app/core/docs.py", root.docs())
    write(base, "app/core/retry.py", root.retry())

    # core/base/ — abstract contracts
    write(base, "app/core/base/__init__.py", "")
    write(base, "app/core/base/repository.py", root.repository())
    write(base, "app/core/base/uow.py", root.unit_of_work())
    write(base, "app/core/base/use_case.py", root.use_case())
    write(base, "app/core/base/markers.py", root.markers())

    if "queue" in integrations:
        with_cache = "cache" in integrations
        write(base, "app/worker.py", root.worker(modules, with_cache))
        write(base, "app/integrations/queue/idempotency.py", integration.queue_idempotency(with_cache))
        write(base, "scripts/start-worker.sh", project.start_worker_sh(), executable=True)


def build_domain(base: Path, name: str, with_cache: bool, minimal: bool) -> None:
    """Create one domain module owning everything it needs."""
    write(base, "app/modules/__init__.py", "")
    mod = f"app/modules/{name}"
    write(base, f"{mod}/__init__.py", "")
    write(base, f"{mod}/constants.py", domain.constants(name))
    write(base, f"{mod}/config.py", domain.config(name))
    write(base, f"{mod}/exceptions.py", domain.exceptions(name))
    write(base, f"{mod}/schemas.py", domain.schemas(name))
    write(base, f"{mod}/models.py", domain.models(name))
    write(base, f"{mod}/rules.py", domain.rules(name))
    write(base, f"{mod}/utils/__init__.py", domain.utils_init(name))
    write(base, f"{mod}/utils/text.py", domain.utils_text(name))
    write(base, f"{mod}/repository.py", domain.repository(name, with_cache))
    write(base, f"{mod}/events.py", domain.events(name))
    write(base, f"{mod}/dependencies.py", domain.dependencies(name, minimal, with_cache))
    write(base, f"{mod}/router.py", domain.router(name))
    write(base, f"{mod}/public.py", domain.public(name))
    write(base, f"{mod}/services/__init__.py", "")
    write(base, f"{mod}/services/read_{name}.py", domain.service_read(name))
    write(base, f"{mod}/services/create_{name}.py", domain.service_write(name, not minimal))

    if not minimal:
        write(base, f"{mod}/uow.py", domain.uow(name, with_cache))

    write(base, f"tests/{name}/__init__.py", "")
    write(base, f"tests/{name}/test_rules.py", test_templates.test_rules(name))
    write(base, f"tests/{name}/test_services.py", test_templates.test_services(name, not minimal))
    write(base, f"tests/{name}/test_router.py", test_templates.test_router(name))


def build_integration(base: Path, name: str) -> None:
    """Create one integration module."""
    renderers = integration.RENDERERS[name]
    mod = f"app/integrations/{name}"
    write(base, "app/integrations/__init__.py", "")
    write(base, f"{mod}/__init__.py", "")
    for filename, render in renderers.items():
        write(base, f"{mod}/{filename}.py", render())


def build_project(
    base: Path, name: str, modules: list[str], integrations: list[str], minimal: bool
) -> None:
    """Create the whole project tree."""
    build_root(base, name, modules, integrations)
    write(base, "tests/__init__.py", "")
    write(base, "tests/conftest.py", test_templates.conftest("cache" in integrations))

    for item in integrations:
        build_integration(base, item)

    with_cache = "cache" in integrations
    for mod in modules:
        build_domain(base, mod, with_cache, minimal)

    if modules:
        write(base, "app/seeds/__init__.py", "")
        write(
            base,
            f"app/seeds/seed_{modules[0]}.py",
            seed_templates.seed_example(modules[0], with_cache),
        )

    write(base, "pyproject.toml", project.pyproject(name, integrations))
    write(base, "docker-compose.yml", project.compose(name, integrations))
    write(base, "docker-compose.prod.yml", project.compose_prod(name, integrations))
    write(base, "Dockerfile", project.dockerfile())
    write(base, "Makefile", project.makefile("queue" in integrations))
    write(base, "scripts/start.sh", project.start_sh(), executable=True)
    write(base, ".env.example", project.env_example(integrations))
    write(base, ".importlinter", project.import_linter(modules, integrations))
    write(base, "alembic.ini", project.alembic_ini())
    write(base, "migrations/env.py", project.alembic_env(modules))
    write(base, "migrations/script.py.mako", project.alembic_mako())
    write(base, "README.md", project.readme(name, modules, integrations))


def wire_module_into_main(base: Path, name: str) -> None:
    """Insert the new module's router into an existing app/main.py, idempotently.

    Textual insertion, not re-rendering root.main(all_modules) from scratch —
    main.py stays "thin, wiring only" by convention (rule #10), but a running
    project may still have hand-added wiring (a second middleware, a custom
    handler) that a full re-render would silently discard. autoformat()'s
    isort pass fixes the exact position afterward, so this only has to land
    the two lines somewhere valid, not in template order.
    """
    main_path = base / "app/main.py"
    content = main_path.read_text(encoding="utf-8")
    import_line = f"from app.modules.{name}.router import router as {name}_router"
    include_line = f'app.include_router({name}_router, prefix="/api/v1")'

    if import_line in content:
        return

    lines = content.split("\n")

    last_import_idx = max(i for i, line in enumerate(lines) if line.startswith(("import ", "from ")))
    lines.insert(last_import_idx + 1, import_line)

    include_indices = [i for i, line in enumerate(lines) if line.startswith("app.include_router(")]
    insert_at = include_indices[-1] + 1 if include_indices else len(lines)
    lines.insert(insert_at, include_line)

    main_path.write_text("\n".join(lines), encoding="utf-8")


def discover_modules(base: Path) -> list[str]:
    """Find every domain module an existing project already has, by its public.py facade."""
    return sorted(p.parent.name for p in (base / "app/modules").glob("*/public.py") if p.is_file())


def discover_integrations(base: Path) -> list[str]:
    """Find every integration an existing project already has."""
    return [i for i in INTEGRATIONS if (base / f"app/integrations/{i}").exists()]


def autoformat(base: Path) -> None:
    """Normalize import order and formatting when ruff is available."""
    if shutil.which("ruff") is None:
        return
    targets = [str(p) for p in (base / "app", base / "tests") if p.exists()]
    subprocess.run(["ruff", "check", "--fix", "-q", *targets], check=False)
    subprocess.run(["ruff", "format", "-q", *targets], check=False)


def main() -> int:
    """Parse arguments and generate the requested artifacts."""
    parser = argparse.ArgumentParser(description="Scaffold a modular FastAPI project")
    parser.add_argument("--name", default="app", help="Project name")
    parser.add_argument("--output", required=True, help="Target directory")
    parser.add_argument("--modules", default="identity", help="Comma separated domain modules")
    parser.add_argument(
        "--integrations",
        default="cache",
        help=f"Comma separated integration modules: {','.join(INTEGRATIONS)}",
    )
    parser.add_argument("--add-module", help="Add one domain module to an existing project")
    parser.add_argument("--add-integration", help="Add one integration module")
    parser.add_argument("--minimal", action="store_true", help="Skip the unit of work layer")
    args = parser.parse_args()

    base = Path(args.output)
    integrations = [i.strip() for i in args.integrations.split(",") if i.strip()]
    unknown = set(integrations) - set(INTEGRATIONS)
    if unknown:
        print(f"unknown integrations: {', '.join(sorted(unknown))}", file=sys.stderr)
        return 1

    if args.add_integration:
        if args.add_integration not in INTEGRATIONS:
            print(f"unknown integration: {args.add_integration}", file=sys.stderr)
            return 1
        build_integration(base, args.add_integration)
        if args.add_integration == "queue":
            existing_modules = discover_modules(base)
            with_cache = (base / "app/integrations/cache").exists()
            write(base, "app/worker.py", root.worker(existing_modules, with_cache))
            write(base, "app/integrations/queue/idempotency.py", integration.queue_idempotency(with_cache))
            write(base, "scripts/start-worker.sh", project.start_worker_sh(), executable=True)
        write(base, ".importlinter", project.import_linter(discover_modules(base), discover_integrations(base)))
        autoformat(base)
        print(f"integration '{args.add_integration}' created at {base}/app/integrations")
        print("wired into .importlinter automatically")
        print("next: open its pool in app/lifespan.py and add the settings to .env")
        return 0

    if args.add_module:
        if not (base / "app").exists():
            print(f"no project found at {base}", file=sys.stderr)
            return 1
        build_domain(base, args.add_module, (base / "app/integrations/cache").exists(), args.minimal)
        wire_module_into_main(base, args.add_module)
        write(base, ".importlinter", project.import_linter(discover_modules(base), discover_integrations(base)))
        autoformat(base)
        print(f"module '{args.add_module}' created at {base}/app/{args.add_module}")
        print("wired into app/main.py and .importlinter automatically — no manual step needed")
        return 0

    modules = [m.strip() for m in args.modules.split(",") if m.strip()]
    build_project(base, args.name, modules, integrations, args.minimal)
    autoformat(base)

    print(f"project '{args.name}' created at {base}")
    print(f"domain modules: {', '.join(modules)}")
    print(f"integration modules: {', '.join(integrations) or 'none'}")
    print("\nnext steps:")
    print("  cp .env.example .env")
    print("  uv sync")
    print("  make up               # or: docker compose up -d --build")
    print("  make migrate          # or: docker compose exec api alembic upgrade head")
    print("  make seed             # runs every app/seeds/seed_*.py, idempotent")
    print("\nfor production: cp .env.example .env.prod (give every secret a new value), then make up ENV=prod")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
