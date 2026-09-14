"""Integration tests for the auth module's DX token repository — real Postgres
via a locally scoped session fixture, mirroring tests/users/test_repository.py.
Nothing here commits: the session is rolled back after each test."""

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.integrations.dx_core.client import DxTokenSet
from app.modules.auth.config import auth_settings
from app.modules.auth.exceptions import DxTokenUnreadable
from app.modules.auth.repository import DxTokenRepository
from app.modules.common.constants import UserStatus
from app.modules.users.models import User


@pytest.fixture
async def _session(engine) -> AsyncIterator[AsyncSession]:
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
        await session.rollback()


@pytest.fixture(autouse=True)
def _dx_token_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth_settings, "DX_TOKEN_FERNET_KEY", SecretStr(Fernet.generate_key().decode()))


async def _user(session: AsyncSession) -> User:
    user = User(email=f"{uuid4()}@example.com", name="DX User", status=UserStatus.ACTIVE)
    session.add(user)
    await session.flush()
    return user


def _token_set(access: str, refresh: str) -> DxTokenSet:
    return DxTokenSet(access_token=access, refresh_token=refresh, expires_in=900, scope="users:view")


class TestDxTokenRepository:
    async def test_stores_both_tokens_encrypted_and_decrypts_them(self, _session: AsyncSession) -> None:
        user = await _user(_session)
        repository = DxTokenRepository(_session)

        await repository.save(user.id, _token_set("dx-at", "dx-rt"), expires_at=datetime.now(UTC))

        row = await repository.get_by_user_id(user.id)
        assert row is not None
        assert row.access_token != "dx-at"
        assert row.refresh_token != "dx-rt"
        assert row.scopes == "users:view"
        assert repository.decrypt_access_token(row) == "dx-at"
        assert repository.decrypt_refresh_token(row) == "dx-rt"

    async def test_save_replaces_the_previous_token_set(self, _session: AsyncSession) -> None:
        user = await _user(_session)
        repository = DxTokenRepository(_session)
        await repository.save(user.id, _token_set("first-at", "first-rt"), expires_at=datetime.now(UTC))

        later = datetime.now(UTC) + timedelta(minutes=15)
        await repository.save(user.id, _token_set("second-at", "second-rt"), expires_at=later)

        row = await repository.get_by_user_id(user.id)
        assert row is not None
        assert repository.decrypt_access_token(row) == "second-at"
        assert repository.decrypt_refresh_token(row) == "second-rt"
        assert row.expires_at == later

    async def test_clear_removes_the_row(self, _session: AsyncSession) -> None:
        user = await _user(_session)
        repository = DxTokenRepository(_session)
        await repository.save(user.id, _token_set("dx-at", "dx-rt"), expires_at=datetime.now(UTC))

        await repository.clear(user.id)

        assert await repository.get_by_user_id(user.id) is None

    async def test_reports_unreadable_tokens_when_the_key_changed(
        self, _session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        user = await _user(_session)
        repository = DxTokenRepository(_session)
        await repository.save(user.id, _token_set("dx-at", "dx-rt"), expires_at=datetime.now(UTC))
        row = await repository.get_by_user_id(user.id)
        assert row is not None
        monkeypatch.setattr(auth_settings, "DX_TOKEN_FERNET_KEY", SecretStr(Fernet.generate_key().decode()))

        with pytest.raises(DxTokenUnreadable):
            repository.decrypt_refresh_token(row)
        with pytest.raises(DxTokenUnreadable):
            repository.decrypt_access_token(row)
