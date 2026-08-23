"""Contract exposed to other modules. Empty for now — no cross-module
consumer needs observability data yet (Decision #1: the Cloudflare Audit
Log tab reuses cloudflare's own 2-layer ACL instead of a facade here)."""

__all__: list[str] = []
