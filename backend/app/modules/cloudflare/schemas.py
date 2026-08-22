"""Schemas for the cloudflare module."""

from datetime import datetime
from uuid import UUID

from app.core.models import CustomModel, FrozenModel
from app.modules.cloudflare.constants import AccessLevel
from app.modules.users.public import UserRead


class CloudflareAccountRead(FrozenModel):
    """Representation safe to round trip through the cache. Never includes api_token."""

    id: UUID
    label: str
    cf_account_id: str
    created_by: UUID | None = None
    created_at: datetime
    updated_at: datetime


class CloudflareAccountCreate(CustomModel):
    """Request body for POST /cloudflare-accounts."""

    label: str
    cf_account_id: str
    api_token: str


class CloudflareAccountUpdate(CustomModel):
    """Request body for PATCH /cloudflare-accounts/{id}. None means unchanged.
    Providing api_token means "rotate the token" and requires OWNER — see
    UpdateCloudflareAccount's use case."""

    label: str | None = None
    api_token: str | None = None


class CloudflareAccountManagerRead(FrozenModel):
    """One manager row, enriched with the target user's email/name (resolved
    via UsersApi in the service layer — the repository only knows user_id)."""

    user_id: UUID
    email: str
    name: str
    access_level: AccessLevel
    created_at: datetime


class CloudflareAccountManagerAssign(CustomModel):
    """Request body for POST /cloudflare-accounts/{id}/managers."""

    user_id: UUID
    access_level: AccessLevel


class CloudflareAccountManagerUpdate(CustomModel):
    """Request body for PATCH /cloudflare-accounts/{id}/managers/{user_id}."""

    access_level: AccessLevel


class TokenRevealResponse(FrozenModel):
    """Response body for POST /cloudflare-accounts/{id}/reveal-token. Never cached."""

    api_token: str


class AccountAccessGrant(FrozenModel):
    """The resolved outcome of a Layer-2 require_account_access check: which
    user, and at what access_level — None means they passed via the
    cloudflare_account:manage_all Layer-1 bypass, which
    CloudflareAccountRules.satisfies_level treats as always-sufficient.

    Lives here (not in dependencies.py, where it's constructed) so both
    dependencies.py AND services/update_account.py can import it without a
    cycle — dependencies.py imports service classes to build its provider
    functions, so a service can never import dependencies.py back."""

    user: UserRead
    held_level: AccessLevel | None
