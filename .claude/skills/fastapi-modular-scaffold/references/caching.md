# Caching reference

## Where this lives

The client, its settings, its constants and its errors are one module:
`app/integrations/cache/`. Key construction is centralized in `keys.py`'s
`CacheKeyBuilder` class; each domain module supplies its own entity name
through its `constants.py` (`{Module}CacheKeys.ENTITY`). Nothing else in the
codebase builds a Redis key.

## Versioned keys

Deleting keys requires knowing every key that exists. Bumping a generation counter does not.

```
ver:user:42        -> 7
user:42:v7:s1      -> payload
```

`INCR ver:user:42` orphans every key of the previous generation in constant time, regardless of how many derived keys exist. Orphans expire on their own TTL. The `s1` suffix is the payload schema version — bump `CacheDefaults.PAYLOAD_SCHEMA_VERSION` in `integrations/cache/constants.py` when the DTO shape changes so a deploy never reads an old-shaped payload into a new model.

## Order of operations

Invalidate strictly after a successful commit. Bumping first opens a window where a concurrent reader loads the pre-commit row and caches it under the new version, leaving wrong data until TTL expiry — a bug that reproduces only under load and is miserable to diagnose.

`UnitOfWork.mark_stale()` queues; `commit()` flushes after the DB commit; `__aexit__` drops the queue on rollback.

## Related entities

The recurring question is what to do when a cached view depends on two tables. Three answers, in order of preference:

**Normalize.** Cache `user` and `tenant` separately, compose in the service. One update touches one key. This is the default and it removes the problem rather than managing it.

**Version-stamped composite.** When the join is too expensive to redo per request, fold every dependency's version into the key: `profile:42:u3:t9`. A tenant update bumps `ver:tenant:7` and every composite key referencing it stops matching — still O(1), still no key enumeration.

**Reverse dependency index.** `SADD dep:tenant:7 <key>` at write time, delete the set members on change. Use only when dependencies are genuinely unpredictable; large tenants produce huge sets and mass deletes.

## Stampede protection

On a cold key, a thousand concurrent requests will each miss and each query. `integrations/cache/client.py` collapses them into one loader call per process.

Across processes this is only per-pod dedup — twenty pods still produce twenty queries. That is usually acceptable. When it is not, add a Redis lock: `SET lock:<key> <token> NX PX 3000`; the winner loads, the losers poll the key briefly and fall back to loading if the lock holder dies.

## Reading defensively

Treat a `ValidationError` on a cached payload as a miss, not an error. Deploys change DTO shapes, and an API that returns 500 because of a stale cache entry is a self-inflicted outage.

```python
try:
    return model.model_validate_json(raw)
except ValidationError:
    logger.warning("stale cache schema key=%s", key)
```

## What not to cache

- Uniqueness checks (`find_by_email` before an insert) — must read fresh
- Anything inside a transaction that the same transaction wrote
- Data whose staleness has money or safety consequences, unless TTL is seconds
- Per-request derived values — that is `Depends` caching, not Redis

## TTL

Keep a TTL even with perfect versioning. It is insurance against the invalidation path you forgot, and it bounds memory. 60–300s for entities; shorter for anything a human watches change.

## Cache is not a database

If Redis goes down, the app should degrade to slow, not to broken. Wrap cache reads so a connection error logs and falls through to the loader. A cache outage that becomes a total outage is a design failure, and it is worth testing by actually killing Redis in staging.
