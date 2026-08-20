# scaffold.py

Generates a modular FastAPI project where each module owns its constants,
config, exceptions and helpers, and each integration is a module of its own.

```bash
python scaffold.py --name shop --output ./shop \
    --modules identity,billing --integrations cache,queue

python scaffold.py --add-module catalog --output ./shop
python scaffold.py --add-integration storage --output ./shop
```

| Flag | Meaning |
|---|---|
| `--name` | Project name, used in config defaults and the database name |
| `--output` | Target directory |
| `--modules` | Comma separated domain modules |
| `--integrations` | `cache`, `queue`, `storage` — omit what is not needed |
| `--add-module` | Add one domain module to an existing project |
| `--add-integration` | Add one integration module |
| `--minimal` | Skip the unit of work layer, for projects under ~15 endpoints |

Templates live in `templates/`: `root.py` for the mechanism-only application
root, `domain.py` for a business module, `integration.py` for cache, queue and
storage, `project.py` for packaging, compose and migrations.

Generated code is auto-formatted with ruff when ruff is on PATH.
