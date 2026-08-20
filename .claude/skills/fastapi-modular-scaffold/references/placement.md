# Placement reference

The single question this file answers: when you write a piece of code, where does it go?

## The test

Ask **who owns the concept**, not what shape the code has. `MAX_SEATS_PER_TENANT` is a number, and `slugify` is a function, but neither fact decides placement. What decides it is that `MAX_SEATS_PER_TENANT` is a fact about tenancy and `slugify` is a fact about text.

A second question resolves most of the remainder: **if this module were extracted into its own service tomorrow, would this code go with it?** If yes, it belongs to the module. If it would have to be duplicated or left behind, it is mechanism and belongs at the root.

*Which file* answers "who owns the concept." A separate rule answers *how it's written once it's there*: a constant is a class attribute, a helper is a `@staticmethod`, never a bare name at module level — see "Grouped into a class" below. That rule doesn't change where anything goes, only how it's shaped once it's there.

## The table

| Code | Location | Why |
|---|---|---|
| `OrderStatus`, `PaymentMethod` | `<module>/constants.py`, as an enum | The enum is a fact about the domain |
| `MAX_SEATS`, `RETRY_LIMIT` | `<module>/constants.py`, as a `Limits`-style class attribute | Business limit, changes with the business |
| `ErrorCode` string enum | `<module>/constants.py` | Client-facing contract of that module |
| `OrderNotFound`, `SeatLimitReached` | `<module>/exceptions.py` | Knows what an order is |
| `AppError`, `NotFoundError` | `app/exceptions.py` | Mechanism: base classes and HTTP mapping |
| `JWT_SECRET`, module TTLs | `<module>/config.py` | Nobody else reads them |
| `DATABASE_URL`, `CORS_ORIGINS`, `ENV` | `app/config.py` | The process needs them to start |
| `can_cancel_order()` | `<module>/rules.py`, as a `@rule`-decorated class's `@staticmethod` | A decision |
| `normalize_email()`, `slugify()` | `<module>/utils/`, as a `@helper`-decorated class's `@staticmethod` | A transform |
| `Page`, `PaginationParams` | `app/pagination.py` | Mechanism, no domain knowledge |
| `CustomModel`, `FrozenModel` | `app/models.py` | Mechanism |
| `Environment` enum | `app/constants.py` | About the process, not the business |
| Redis key construction | `integrations/cache/keys.py`, as a `CacheKeyBuilder`-style class | One place, or invalidation cannot be reasoned about |

## Grouped into a class

The file a constant or helper lives in doesn't change — that's what the table above answers. What
changes is that nothing sits bare at module level inside that file. `MAX_SEATS` isn't a loose
`MAX_SEATS = 50` above the file's classes; it's `OrderLimits.MAX_SEATS`, a class attribute, grouped
with the other limits that concern. `slugify` isn't a bare `def slugify(...)`; it's a `@staticmethod`
on a class in `utils/` — a package, one file and one class per concern, the same way `services/` is
one file per use case once a module has more than one.

This is still imported and used from that class, from wherever it's needed — that half is unchanged.
The rule is about shape within the owning file, not about where cross-module access goes through
(`public.py` still owns that). It does not reach `router.py`, `dependencies.py` or `lifespan.py` — a
FastAPI dependency provider is a plain function `Depends()` calls directly, a framework entry point,
not the scattered helper this rule targets. See `references/layer-examples.md` for the full pattern,
including the `@database`/`@helper`/`@rule`/`@use_case`/`@facade` markers in `app/markers.py` that tag
each class with its role.

## rules.py against utils/

Both hold methods with no I/O, so the split looks arbitrary until you watch them age.

`rules.py` encodes decisions: it answers yes or no, or picks between outcomes, and it changes when the business changes. `can_transition`, `is_eligible_for_refund`, `requires_approval` — one `@rule`-decorated class.

`utils/` reshapes data: it answers "what does this look like in another form", and it changes when a format changes. `normalize_email`, `slugify`, `mask_card_number` — one `@helper`-decorated class per concern (`utils/text.py`, `utils/money.py`), not one file that keeps growing.

Holding the split gives two payoffs. Rules stay small enough that heavy test coverage is cheap, and a reviewer asked "did the business logic change in this PR" can answer by looking at one file. Merged into a single `helpers.py`, both properties disappear within months.

## Why exceptions stay in the module

The instinct to collect every error into one global file is strong and worth resisting.

`OrderNotFound` encodes domain knowledge: that orders exist, and what counts as one being missing. Moving it to a global file means that file gradually learns about orders, payments, users, invoices and shipments — it becomes a map of the whole system that every module imports and any module can break. Changing one module's error then requires touching a file three other teams depend on.

What genuinely belongs at the root is the *mechanism*: the `AppError` base carrying `code` and `status_code`, the subclass bases (`NotFoundError`, `ConflictError`), and the single handler in `main.py` that maps them. That is stable and knows nothing about any domain.

So: base classes centralized, error catalogue distributed.

## Integrations are modules

`cache`, `queue` and `storage` are not utilities. Each has settings, constants, failure modes and a client. Flattened into `shared/`, those concerns scatter: the Redis URL drifts into global config, the TTL constant into a global constants file, the connection error into a global exceptions file, and nothing indicates they belong together.

As a module, `integrations/cache/` holds all four and can be read, reviewed, tested and replaced as one unit. Swapping Redis for something else touches one directory.

The only structural difference from a domain module is absence: no `models.py` (owns no tables), no `router.py` (exposes no HTTP), no `rules.py` (holds no business decisions).

## Warning signs

Each of these means the boundary has already leaked:

- `app/utils.py`, `app/utils/` or `app/helpers.py` exists at the root
- `app/exceptions.py` mentions a domain entity by name
- `app/constants.py` holds a business limit
- Global `Config` has a setting only one module reads
- Two modules import the same helper from a third module that is neither's owner
- A module's `constants.py` imports from another module's `constants.py`
- A bare `NAME = value` or a bare `def helper(...)` sits above a class in `constants.py`, `rules.py` or a file inside `utils/` — the concept still needs an owning class, not just an owning file

The last one is the most serious: it means two modules share a concept, and the concept has no owner. Either it belongs to one of them and the other should go through `public.py`, or it is genuinely universal and belongs at the root — but that case is rarer than it first appears, and duplicating a constant is often cheaper than coupling two modules to share it.

## When duplication is correct

Sharing has a cost that is invisible at the moment you introduce it and obvious a year later: every change to a shared thing needs coordination across everyone who uses it. Two modules each holding their own `MAX_RETRIES = 3` are free to diverge when their needs diverge. One shared `MAX_RETRIES` means the first divergence turns into an argument or a parameter.

Duplicate until three modules need the same thing *and* it is stable *and* divergence would be a bug rather than a feature. Only then promote it, and promote the smallest possible version.
