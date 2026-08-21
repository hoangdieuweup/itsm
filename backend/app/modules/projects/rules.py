"""Business rules for the projects module.

Everything here is a pure decision: no I/O, no framework, no database.
"""

from app.core.base.markers import rule
from app.modules.projects.config import projects_settings
from app.modules.projects.constants import ProjectLinkType


class ProjectsRules:
    """Every business decision about a project."""

    @staticmethod
    @rule
    def default_links() -> list[tuple[ProjectLinkType, str, str]]:
        """Return the (type, name, url) rows auto-attached to every new
        project — internal WeUp Jira/Git, marked is_default by the caller.
        An unconfigured URL means no default link of that kind, not a link
        pointing at an empty string."""
        candidates = [
            (ProjectLinkType.JIRA, "Jira", projects_settings.DEFAULT_JIRA_URL),
            (ProjectLinkType.GIT, "Git", projects_settings.DEFAULT_GIT_URL),
        ]
        return [(link_type, name, url) for link_type, name, url in candidates if url]
