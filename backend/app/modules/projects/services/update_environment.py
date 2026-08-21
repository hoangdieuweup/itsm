from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.projects.exceptions import EnvironmentNotFound
from app.modules.projects.schemas import EnvironmentRead
from app.modules.projects.uow import AbstractProjectsUnitOfWork


class UpdateEnvironment(AbstractUseCase):
    """Rename and/or re-point an environment. type is immutable — see schemas.EnvironmentUpdate."""

    def __init__(self, uow: AbstractProjectsUnitOfWork) -> None:
        self._uow = uow

    @use_case
    async def execute(
        self, environment_id: UUID, *, name: str | None, base_url: str | None
    ) -> EnvironmentRead:
        if await self._uow.environments.get_by_id(environment_id) is None:
            raise EnvironmentNotFound()
        updated = await self._uow.environments.update(environment_id, name=name, base_url=base_url)
        await self._uow.commit()
        return updated
