"""Smoke test: every new Phase 4 symbol exists and imports cleanly. Real
behavior is exercised by test_rules.py/test_client.py/test_services.py/
test_router.py — this only guards against a typo'd name breaking every
downstream import at once."""


def test_new_symbols_import() -> None:
    from app.modules.cloudflare.constants import (
        CloudflareDnsAuditActions,
        DnsRecordType,
        ErrorCode,
        LogSource,
        ManagedBy,
    )
    from app.modules.cloudflare.exceptions import (
        CloudflareConfigAlreadyExists,
        CloudflareConfigNotFound,
        CloudflareDnsOperationRejected,
        CloudflareEnvironmentNotFound,
        DnsRecordNotFound,
        DnsRecordSyncFailed,
        MissingDnsRecordPriority,
        ZoneNotOwnedByAccount,
    )
    from app.modules.cloudflare.models import CloudflareConfig, DnsRecord
    from app.modules.cloudflare.schemas import (
        CloudflareConfigCreate,
        CloudflareConfigRead,
        DnsRecordCreate,
        DnsRecordRead,
        DnsRecordUpdate,
        ZoneOption,
    )

    assert DnsRecordType.MX == "MX"
    assert LogSource.AUDIT_LOG == "audit_log"
    assert ManagedBy.SYSTEM == "system"
    assert ErrorCode.CONFIG_NOT_FOUND == "cloudflare_config_not_found"
    assert CloudflareDnsAuditActions.DNS_RECORD_CREATED == "CLOUDFLARE_DNS_RECORD_CREATED"
    assert issubclass(CloudflareConfigNotFound, Exception)
    assert issubclass(CloudflareConfigAlreadyExists, Exception)
    assert issubclass(CloudflareEnvironmentNotFound, Exception)
    assert issubclass(DnsRecordNotFound, Exception)
    assert issubclass(ZoneNotOwnedByAccount, Exception)
    assert issubclass(MissingDnsRecordPriority, Exception)
    assert issubclass(CloudflareDnsOperationRejected, Exception)
    assert issubclass(DnsRecordSyncFailed, Exception)
    assert CloudflareConfig.__tablename__ == "cloudflare_configs"
    assert DnsRecord.__tablename__ == "dns_records"
    zone = ZoneOption(id="z1", name="example.com")
    assert zone.name == "example.com"
