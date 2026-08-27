"""Wire schemas owned by the cloudflare integration — shapes returned
directly by the Cloudflare REST API, not persisted anywhere."""

from app.core.models import FrozenModel


class ZoneOption(FrozenModel):
    """One zone available to bind, from GET /zones?account.id=."""

    id: str
    name: str


class CloudflareTrafficBucket(FrozenModel):
    """One hourly bucket of aggregated HTTP request traffic, from the
    GraphQL Analytics API's httpRequestsAdaptiveGroups node."""

    bucket_start: str
    requests: int
    bytes: int


class CloudflareTrafficStatusCount(FrozenModel):
    """Request count for one edge HTTP response status code."""

    status: int
    requests: int


class CloudflareTrafficStats(FrozenModel):
    """Aggregated traffic for one environment's own hostname, over a caller
    -supplied time range — deliberately narrow (no chart-library-shaped
    payload, no raw per-request rows: Logpull/Logpush are Enterprise-only,
    this is the Free-plan-compatible GraphQL Analytics substitute)."""

    hostname: str
    total_requests: int
    total_bytes: int
    buckets: list[CloudflareTrafficBucket]
    status_codes: list[CloudflareTrafficStatusCount]
