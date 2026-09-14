"""Single access path to the dx_tokens table.

Not an AbstractRepository[T]: that contract is shaped for a paginated,
id-addressable entity (get_by_id/list_page), but this store is a single
encrypted row per user with no listing use case — forcing it into that shape
would add an unused list_page implementation for no benefit. See
references/layer-examples.md for when AbstractRepository is (and isn't) the
right fit.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.markers import database, helper
from app.core.crypto import FernetCodec
from app.core.exceptions import SecretUnreadableError
from app.integrations.dx_core.client import DxTokenSet
from app.modules.auth.config import auth_settings
from app.modules.auth.exceptions import DxTokenUnreadable
from app.modules.auth.models import DxToken


class AbstractDxTokenRepository(ABC):
    """Contract a use case depends on instead of the concrete SQLAlchemy class below."""

    @abstractmethod
    async def get_by_user_id(self, user_id: UUID) -> DxToken | None:
        """Return the encrypted DX token row for a user, or None if never linked."""
        raise NotImplementedError

    @abstractmethod
    async def save(self, user_id: UUID, token: DxTokenSet, *, expires_at: datetime) -> None:
        """Upsert a user's DX token set, encrypting both tokens at rest."""
        raise NotImplementedError

    @abstractmethod
    async def clear(self, user_id: UUID) -> None:
        """Delete a user's DX token row (logout, or a rejected refresh)."""
        raise NotImplementedError

    @abstractmethod
    def decrypt_access_token(self, row: DxToken) -> str:
        """Decrypt a row's access token for one-off outbound use (e.g. revoke)."""
        raise NotImplementedError

    @abstractmethod
    def decrypt_refresh_token(self, row: DxToken) -> str:
        """Decrypt a row's refresh token for one-off outbound use (e.g. revoke)."""
        raise NotImplementedError


class DxTokenRepository(AbstractDxTokenRepository):
    """SQLAlchemy implementation. Every read/write of dx_tokens goes through this class."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @database
    async def get_by_user_id(self, user_id: UUID) -> DxToken | None:
        """Return the encrypted DX token row for a user, or None if never linked."""
        return await self._session.scalar(select(DxToken).where(DxToken.user_id == user_id))

    @database
    async def save(self, user_id: UUID, token: DxTokenSet, *, expires_at: datetime) -> None:
        """Upsert a user's DX token set, encrypting both tokens at rest.

        DX rotates the refresh token on every exchange, so both tokens are
        always replaced together — never patched independently.
        """
        row = await self.get_by_user_id(user_id)
        if row is None:
            row = DxToken(user_id=user_id)
            self._session.add(row)
        row.access_token = self._encrypt(token.access_token)
        row.refresh_token = self._encrypt(token.refresh_token)
        row.expires_at = expires_at
        row.scopes = token.scope
        await self._session.flush()

    @database
    async def clear(self, user_id: UUID) -> None:
        """Delete a user's DX token row (logout, or a rejected refresh)."""
        row = await self.get_by_user_id(user_id)
        if row is not None:
            await self._session.delete(row)
            await self._session.flush()

    @helper
    def decrypt_access_token(self, row: DxToken) -> str:
        """Decrypt a row's access token for one-off outbound use (e.g. revoke)."""
        return self._decrypt(row.access_token)

    @helper
    def decrypt_refresh_token(self, row: DxToken) -> str:
        """Decrypt a row's refresh token for one-off outbound use (e.g. revoke)."""
        return self._decrypt(row.refresh_token)

    @helper
    def _encrypt(self, plaintext: str) -> str:
        """Encrypt one token value with the auth module's DX token key."""
        return FernetCodec.encrypt(plaintext, key=auth_settings.DX_TOKEN_FERNET_KEY.get_secret_value())

    @helper
    def _decrypt(self, ciphertext: str) -> str:
        """Decrypt one token value with the auth module's DX token key, raising
        DxTokenUnreadable when it was encrypted under another key or no valid key is set."""
        try:
            return FernetCodec.decrypt(ciphertext, key=auth_settings.DX_TOKEN_FERNET_KEY.get_secret_value())
        except SecretUnreadableError as exc:
            raise DxTokenUnreadable() from exc
