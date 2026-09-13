"""Single access path to the notification_channels table. Owns the only
place secret sub-fields within `config` get encrypted (on write) and
masked (on read)."""

from abc import abstractmethod
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base.markers import database, helper
from app.core.base.repository import AbstractRepository
from app.core.crypto import FernetCodec
from app.modules.notifications.config import notifications_settings
from app.modules.notifications.constants import NotificationChannelSecrets, NotificationChannelType
from app.modules.notifications.exceptions import NotificationChannelNotFound
from app.modules.notifications.models import NotificationChannel
from app.modules.notifications.schemas import NotificationChannelRead


class AbstractNotificationChannelRepository(AbstractRepository[NotificationChannelRead, UUID]):
    @abstractmethod
    async def list_for_project(
        self, project_id: UUID, *, environment_id: UUID | None
    ) -> list[NotificationChannelRead]:
        raise NotImplementedError

    @abstractmethod
    async def create(
        self,
        *,
        project_id: UUID,
        environment_id: UUID | None,
        type: NotificationChannelType,
        name: str,
        config: dict,
    ) -> NotificationChannelRead:
        raise NotImplementedError

    @abstractmethod
    async def update(
        self,
        channel_id: UUID,
        *,
        name: str | None,
        config: dict | None,
        is_active: bool | None,
    ) -> NotificationChannelRead:
        raise NotImplementedError

    @abstractmethod
    async def delete(self, channel_id: UUID) -> None:
        raise NotImplementedError

    @abstractmethod
    async def get_config_ciphertext_fields(self, channel_id: UUID) -> dict:
        """Returns the raw stored config (secret sub-field still ciphertext,
        everything else plaintext) — for the send path only, bypassing
        NotificationChannelRead's masking entirely."""
        raise NotImplementedError


class NotificationChannelRepository(AbstractNotificationChannelRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    @helper
    def _mask_config(channel_type: NotificationChannelType, config: dict) -> dict:
        """Replaces a type's known secret field (if any) with a has_<field>
        boolean, leaving every other key as-is. OTHER has no known secret
        field, so its config passes through unmasked — there's nothing to mask
        by definition."""
        secret_field = NotificationChannelSecrets.FIELDS_BY_TYPE.get(channel_type)
        if secret_field is None:
            return dict(config)
        masked = {k: v for k, v in config.items() if k != secret_field}
        masked[f"has_{secret_field}"] = secret_field in config and bool(config[secret_field])
        return masked

    @staticmethod
    @helper
    def _encrypt_config(channel_type: NotificationChannelType, config: dict) -> dict:
        secret_field = NotificationChannelSecrets.FIELDS_BY_TYPE.get(channel_type)
        if secret_field is None or secret_field not in config:
            return dict(config)
        encrypted = dict(config)
        encrypted[secret_field] = FernetCodec.encrypt(
            config[secret_field], key=notifications_settings.FERNET_KEY
        )
        return encrypted

    @classmethod
    @helper
    def _to_read(cls, row: NotificationChannel) -> NotificationChannelRead:
        return NotificationChannelRead(
            id=row.id,
            project_id=row.project_id,
            environment_id=row.environment_id,
            type=row.type,
            name=row.name,
            config=cls._mask_config(row.type, row.config),
            is_active=row.is_active,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    @database
    async def get_by_id(self, entity_id: UUID) -> NotificationChannelRead | None:
        row = await self._session.get(NotificationChannel, entity_id)
        return self._to_read(row) if row else None

    @database
    async def list_page(self, limit: int, offset: int) -> tuple[list[NotificationChannelRead], int]:
        rows = await self._session.scalars(
            select(NotificationChannel).order_by(NotificationChannel.id).limit(limit).offset(offset)
        )
        items = [self._to_read(row) for row in rows]
        total = await self._session.scalar(select(func.count()).select_from(NotificationChannel))
        return items, total or 0

    @database
    async def list_for_project(
        self, project_id: UUID, *, environment_id: UUID | None
    ) -> list[NotificationChannelRead]:
        stmt = select(NotificationChannel).where(NotificationChannel.project_id == project_id)
        if environment_id is not None:
            stmt = stmt.where(
                (NotificationChannel.environment_id == environment_id)
                | (NotificationChannel.environment_id.is_(None))
            )
        rows = await self._session.scalars(stmt.order_by(NotificationChannel.name))
        return [self._to_read(row) for row in rows]

    @database
    async def create(
        self,
        *,
        project_id: UUID,
        environment_id: UUID | None,
        type: NotificationChannelType,
        name: str,
        config: dict,
    ) -> NotificationChannelRead:
        row = NotificationChannel(
            project_id=project_id,
            environment_id=environment_id,
            type=type,
            name=name,
            config=self._encrypt_config(type, config),
        )
        self._session.add(row)
        await self._session.flush()
        await self._session.refresh(row)
        return self._to_read(row)

    @database
    async def update(
        self,
        channel_id: UUID,
        *,
        name: str | None,
        config: dict | None,
        is_active: bool | None,
    ) -> NotificationChannelRead:
        row = await self._session.get(NotificationChannel, channel_id)
        if row is None:
            raise NotificationChannelNotFound()
        if name is not None:
            row.name = name
        if config is not None:
            row.config = self._encrypt_config(row.type, config)
        if is_active is not None:
            row.is_active = is_active
        await self._session.flush()
        await self._session.refresh(row)
        return self._to_read(row)

    @database
    async def delete(self, channel_id: UUID) -> None:
        row = await self._session.get(NotificationChannel, channel_id)
        if row is not None:
            await self._session.delete(row)
            await self._session.flush()

    @database
    async def get_config_ciphertext_fields(self, channel_id: UUID) -> dict:
        row = await self._session.get(NotificationChannel, channel_id)
        return dict(row.config) if row is not None else {}
