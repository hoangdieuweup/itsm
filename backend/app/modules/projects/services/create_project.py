from app.core.base.markers import use_case
from app.core.base.use_case import AbstractUseCase
from app.modules.projects.rules import ProjectsRules
from app.modules.projects.schemas import ProjectRead
from app.modules.projects.uow import AbstractProjectsUnitOfWork


class CreateProject(AbstractUseCase):
    """Create a project, then attach the configured default Jira/Git links
    (ProjectsRules.default_links) — see spec's project_links note: these are
    seeded values, not a template table, so nothing here is admin-editable."""

    def __init__(self, uow: AbstractProjectsUnitOfWork) -> None:
        self._uow = uow

    @use_case
    async def execute(self, name: str, description: str | None) -> ProjectRead:
        project = await self._uow.projects.create(name=name, description=description, created_by=None)
        for link_type, link_name, url in ProjectsRules.default_links():
            await self._uow.project_links.create(
                project_id=project.id, type=link_type, name=link_name, url=url, is_default=True
            )
        await self._uow.commit()
        return project
