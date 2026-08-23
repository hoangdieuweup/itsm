"""Wire schemas owned by the cloudflare integration — shapes returned
directly by the Cloudflare REST API, not persisted anywhere."""

from app.core.models import FrozenModel


class ZoneOption(FrozenModel):
    """One zone available to bind, from GET /zones?account.id=."""

    id: str
    name: str


class CloudflareAuditLogEntry(FrozenModel):
    """A deliberately narrow, purpose-built read-model of one Cloudflare
    account audit log entry — not a pass-through of Cloudflare's full (large,
    evolving) entry shape. Extend with more fields only when a real consumer
    needs them (e.g. a future phase wanting resource.id for deep-linking)."""

    id: str
    when: str
    actor_email: str | None
    actor_ip: str | None
    action_type: str
    resource_type: str | None
    resource_product: str | None
    new_value: str | None
