"""Business rules for the projects module.

Everything here is a pure decision: no I/O, no framework, no database.
"""

from app.core.base.markers import rule
from app.modules.projects.config import projects_settings
from app.modules.projects.constants import ProjectLinkType, ProjectScopedPermissionCatalog


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


class ProjectRoleRules:
    """Every business decision about project-scoped roles — the union/
    allowlist boundary a ProjectRole's effective permissions are computed
    through, expressed as pure functions."""

    @staticmethod
    @rule
    def assignable_keys() -> frozenset[tuple[str, str]]:
        """The bounded set a ProjectRole may ever grant."""
        return ProjectScopedPermissionCatalog.ASSIGNABLE

    @staticmethod
    @rule
    def rejects_unassignable(keys: list[tuple[str, str]]) -> list[tuple[str, str]]:
        """Return the subset of keys NOT in the allowlist. Empty = every
        key is acceptable to assign to a project role."""
        assignable = ProjectRoleRules.assignable_keys()
        return [key for key in keys if key not in assignable]

    @staticmethod
    @rule
    def effective_permissions(global_keys: frozenset[str], project_keys: frozenset[str]) -> frozenset[str]:
        """A project role GRANTS on top of the caller's global
        permissions — the union, never a narrowing. A member with no
        project role assigned has project_keys=frozenset(), so this
        returns exactly their global set — byte-for-byte today's
        pre-project-role behavior. Flipping to narrow semantics later is
        a one-line change here (intersection instead of union)."""
        return global_keys | project_keys
