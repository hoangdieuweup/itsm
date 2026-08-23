"""First-ever tests of CacheClient.try_acquire_lock/release_lock — these
methods have existed since an earlier phase but had zero call sites or
tests until Phase 5's Tunnel ingress-array locking became their first
real usage."""

import asyncio

from app.integrations.cache.client import CacheClient


class TestTryAcquireLock:
    async def test_first_caller_acquires(self, cache_client: CacheClient) -> None:
        acquired = await cache_client.try_acquire_lock("lock:tunnel:t1", ttl=5)
        assert acquired is True

    async def test_second_caller_is_rejected_while_held(self, cache_client: CacheClient) -> None:
        first = await cache_client.try_acquire_lock("lock:tunnel:t1", ttl=5)
        second = await cache_client.try_acquire_lock("lock:tunnel:t1", ttl=5)
        assert first is True
        assert second is False

    async def test_release_then_reacquire_succeeds(self, cache_client: CacheClient) -> None:
        await cache_client.try_acquire_lock("lock:tunnel:t1", ttl=5)
        await cache_client.release_lock("lock:tunnel:t1")
        reacquired = await cache_client.try_acquire_lock("lock:tunnel:t1", ttl=5)
        assert reacquired is True

    async def test_release_of_unheld_lock_is_a_safe_noop(self, cache_client: CacheClient) -> None:
        await cache_client.release_lock("lock:tunnel:never-held")

    async def test_expiry_releases_the_lock_automatically(self, cache_client: CacheClient) -> None:
        await cache_client.try_acquire_lock("lock:tunnel:t1", ttl=1)
        await asyncio.sleep(1.2)
        reacquired = await cache_client.try_acquire_lock("lock:tunnel:t1", ttl=5)
        assert reacquired is True

    async def test_different_keys_do_not_contend(self, cache_client: CacheClient) -> None:
        first = await cache_client.try_acquire_lock("lock:tunnel:t1", ttl=5)
        second = await cache_client.try_acquire_lock("lock:tunnel:t2", ttl=5)
        assert first is True
        assert second is True

    async def test_concurrent_acquire_attempts_only_one_wins(self, cache_client: CacheClient) -> None:
        """Proves the lock actually serializes under real concurrency, not
        just sequential calls — two coroutines race for the same key."""
        results = await asyncio.gather(
            cache_client.try_acquire_lock("lock:tunnel:race", ttl=5),
            cache_client.try_acquire_lock("lock:tunnel:race", ttl=5),
        )
        assert sorted(results) == [False, True]
