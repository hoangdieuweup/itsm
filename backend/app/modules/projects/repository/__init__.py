"""Single access path to the projects module's tables, one file per aggregate. Every class
is re-exported here so callers keep importing from app.modules.projects.repository."""

from app.modules.projects.repository.environments import (
    AbstractEnvironmentRepository,
    EnvironmentRepository,
)
from app.modules.projects.repository.links import (
    AbstractProjectLinkRepository,
    ProjectLinkRepository,
)
from app.modules.projects.repository.members import (
    AbstractProjectMemberRepository,
    ProjectMemberRepository,
    ProjectMemberRow,
)
from app.modules.projects.repository.projects import (
    AbstractProjectRepository,
    ProjectRepository,
)
from app.modules.projects.repository.roles import (
    AbstractProjectRoleRepository,
    ProjectRoleRepository,
    ProjectRoleRow,
)

__all__ = [
    "AbstractEnvironmentRepository",
    "AbstractProjectLinkRepository",
    "AbstractProjectMemberRepository",
    "AbstractProjectRepository",
    "AbstractProjectRoleRepository",
    "EnvironmentRepository",
    "ProjectLinkRepository",
    "ProjectMemberRepository",
    "ProjectMemberRow",
    "ProjectRepository",
    "ProjectRoleRepository",
    "ProjectRoleRow",
]
