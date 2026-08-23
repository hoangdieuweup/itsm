"""Smoke test: every new Phase 5 symbol exists and imports cleanly."""

from app.modules.cloudflare.constants import CloudflareTunnelAuditActions, ErrorCode, TunnelStatus
from app.modules.cloudflare.exceptions import (
    CloudflareTunnelNotFound,
    TunnelConfigLocked,
    TunnelHostnameAlreadyExists,
    TunnelIngressSyncFailed,
    TunnelPublicHostnameNotFound,
)
from app.modules.cloudflare.models import CloudflareTunnel, TunnelPublicHostname
from app.modules.cloudflare.schemas import (
    CloudflareTunnelCreate,
    CloudflareTunnelRead,
    TunnelPublicHostnameCreate,
    TunnelPublicHostnameRead,
    TunnelPublicHostnameUpdate,
    TunnelTokenResponse,
)


def test_new_symbols_import() -> None:
    assert TunnelStatus.UNKNOWN == "unknown"
    assert TunnelStatus.HEALTHY == "healthy"
    assert ErrorCode.TUNNEL_NOT_FOUND == "cloudflare_tunnel_not_found"
    assert CloudflareTunnelAuditActions.TUNNEL_CREATED == "CLOUDFLARE_TUNNEL_CREATED"
    assert issubclass(CloudflareTunnelNotFound, Exception)
    assert issubclass(TunnelPublicHostnameNotFound, Exception)
    assert issubclass(TunnelConfigLocked, Exception)
    assert issubclass(TunnelHostnameAlreadyExists, Exception)
    assert issubclass(TunnelIngressSyncFailed, Exception)
    assert CloudflareTunnel.__tablename__ == "cloudflare_tunnels"
    assert TunnelPublicHostname.__tablename__ == "tunnel_public_hostnames"
    assert "cf_tunnel_id" in CloudflareTunnelRead.model_fields
    assert "name" in CloudflareTunnelCreate.model_fields
    assert "token" in TunnelTokenResponse.model_fields
    assert "hostname" in TunnelPublicHostnameRead.model_fields
    assert "hostname" in TunnelPublicHostnameCreate.model_fields
    assert "service" in TunnelPublicHostnameUpdate.model_fields
