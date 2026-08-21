"""Integration tests for app.modules.audit.router — real Postgres + MongoDB via testcontainers."""

from uuid import UUID

from httpx import AsyncClient
from motor.motor_asyncio import AsyncIOMotorDatabase
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.security import JwtCodec
from app.modules.audit.constants import AuditEventType, AuditSeverity, AuditSource
from app.modules.audit.public import AuditApi
from app.modules.audit.repository import MongoAuditLogRepository
from app.modules.audit.schemas import AuditActor
from app.modules.auth.config import auth_settings
from app.modules.auth.constants import AuthCookies
from app.modules.rbac.models import Permission, Role, RolePermission, UserRole
from app.modules.users.models import User


async def _login_with_permissions(
    client: AsyncClient, engine: AsyncEngine, *, permissions: list[tuple[str, str]]
) -> UUID:
    async with engine.begin() as conn:
        user_result = await conn.execute(
            insert(User).values(
                email="actor@example.com",
                name="Actor",
                status="active",
                external_user_id="dx-actor",
                employee_code=None,
                email_confirmed=True,
            )
        )
        user_id = user_result.inserted_primary_key[0]
        role_result = await conn.execute(insert(Role).values(name="test-role", is_system=False))
        role_id = role_result.inserted_primary_key[0]
        for resource, action in permissions:
            perm_result = await conn.execute(
                insert(Permission).values(resource=resource, action=action, description_key="x")
            )
            permission_id = perm_result.inserted_primary_key[0]
            await conn.execute(insert(RolePermission).values(role_id=role_id, permission_id=permission_id))
        await conn.execute(insert(UserRole).values(user_id=user_id, role_id=role_id))

    token = JwtCodec.encode(
        {"sub": str(user_id), "type": "access", "jti": "test-jti"},
        secret=auth_settings.JWT_SECRET,
        ttl_seconds=3600,
    )
    client.cookies.set(AuthCookies.ACCESS_TOKEN, token)
    return user_id


class TestListAuditLogs:
    async def test_requires_audit_log_read_permission(
        self, client: AsyncClient, engine: AsyncEngine
    ) -> None:
        await _login_with_permissions(client, engine, permissions=[])

        response = await client.get("/api/v1/audit-logs")

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "rbac_permission_denied"

    async def test_lists_entries_with_permission(
        self, client: AsyncClient, engine: AsyncEngine, mongo_db: AsyncIOMotorDatabase
    ) -> None:
        await _login_with_permissions(client, engine, permissions=[("audit_log", "read")])
        api = AuditApi(MongoAuditLogRepository(mongo_db))
        await api.log_event(
            type=AuditEventType.AUDIT,
            source=AuditSource.USER_ACTION,
            action="PROJECT_CREATED",
            severity=AuditSeverity.INFO,
            message="seeded for router test",
            actor=AuditActor(),
        )

        response = await client.get("/api/v1/audit-logs")

        body = response.json()
        assert response.status_code == 200
        assert body["data"]["total"] == 1
        assert body["data"]["items"][0]["action"] == "PROJECT_CREATED"
