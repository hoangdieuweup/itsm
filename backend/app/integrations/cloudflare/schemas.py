"""Wire schemas owned by the cloudflare integration — shapes returned
directly by the Cloudflare REST API, not persisted anywhere."""

from app.core.models import FrozenModel


class ZoneOption(FrozenModel):
    """One zone available to bind, from GET /zones?account.id=."""

    id: str
    name: str
