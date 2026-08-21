from uuid import UUID

from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.projects.exceptions import EnvironmentNotFound
from app.modules.projects.uow import AbstractProjectsUnitOfWork


class DeleteEnvironment(AbstractUseCase):
    """Delete an environment."""

    def __init__(self, uow: AbstractProjectsUnitOfWork) -> None:
        self._uow = uow

    @use_case
    async def execute(self, environment_id: UUID) -> None:
        if await self._uow.environments.get_by_id(environment_id) is None:
            raise EnvironmentNotFound()
        await self._uow.environments.delete(environment_id)
        await self._uow.commit()
