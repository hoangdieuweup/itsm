"""Contract exposed to other modules. This is the ONLY file another module
may import from cloudflare — enforced by scripts/check_module_boundaries.py
and the cloudflare-facade contract in .importlinter.

Empty in Phase 3: no other module needs cross-module access to cloudflare
yet. Phase 4 (DNS binding) is expected to add a facade method here — e.g.
"resolve a ready CloudflareClient + decrypted token for an account_id" — so
DNS reaches Cloudflare through this facade instead of cloudflare's internals
directly.
"""

__all__: list[str] = []
