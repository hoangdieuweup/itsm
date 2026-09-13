"""Unit tests for app.modules.projects.rules — pure decisions, no I/O."""

from app.modules.projects.rules import ProjectRoleRules
from app.modules.rbac.constants import RbacPermissionCatalog, RbacScoping


class TestAssignableKeys:
    def test_includes_environment_update_but_not_project_delete(self) -> None:
        keys = ProjectRoleRules.assignable_keys()
        assert ("environment", "update") in keys
        assert ("project", "delete") not in keys
        assert ("project", "manage_all") not in keys
        assert ("project_member", "manage") not in keys
        assert ("project_role", "read") not in keys
        assert ("project_role", "manage") not in keys
        assert ("user", "update_status") not in keys

    def test_only_project_prefixed_cloudflare_and_observability_atoms(self) -> None:
        keys = ProjectRoleRules.assignable_keys()
        assert ("project_cloudflare_dns", "create") in keys
        assert ("project_cloudflare_tunnel", "create") in keys
        assert ("project_cloudflare_hostname", "update") in keys
        assert ("project_cloudflare_config", "read") in keys
        assert ("environment_cloudflare_traffic", "read") in keys
        assert ("project_loki_config", "manage") in keys
        assert ("project_alert_rule", "create") in keys
        assert ("project_incident", "acknowledge") in keys

    def test_excludes_cloudflare_account_administration_and_binding(self) -> None:
        keys = ProjectRoleRules.assignable_keys()
        assert ("cloudflare_account", "create") not in keys
        assert ("cloudflare_account", "delete") not in keys
        assert ("cloudflare_account", "reveal_token") not in keys
        assert ("cloudflare_account", "manage_all") not in keys
        assert ("cloudflare_manager", "read") not in keys
        assert ("cloudflare_manager", "manage") not in keys
        assert ("cloudflare_config", "manage") not in keys

    def test_no_account_level_resource_is_assignable_under_its_old_name(self) -> None:
        """Regression guard for the exact escalation this split closes: an
        account-level resource string must NEVER re-enter ASSIGNABLE."""
        account_level = {
            "cloudflare_account",
            "cloudflare_manager",
            "cloudflare_config",
            "cloudflare_tunnel",
            "cloudflare_hostname",
            "cloudflare_dns",
            "cloudflare_traffic",
            "loki_config",
            "alert_rule",
            "incident",
        }
        offenders = [k for k in ProjectRoleRules.assignable_keys() if k[0] in account_level]
        assert offenders == []

    def test_tunnel_delete_and_reveal_token_are_unassignable_under_any_name(self) -> None:
        keys = ProjectRoleRules.assignable_keys()
        assert ("cloudflare_tunnel", "delete") not in keys
        assert ("cloudflare_tunnel", "reveal_token") not in keys
        assert ("project_cloudflare_tunnel", "delete") not in keys
        assert ("project_cloudflare_tunnel", "reveal_token") not in keys

    def test_every_assignable_key_exists_in_the_rbac_catalog(self) -> None:
        """A tuple in ASSIGNABLE with no matching CATALOG row can never be
        granted (no Permission id exists) — a silent dead entry."""
        catalog = {(r, a) for r, a, _ in RbacPermissionCatalog.CATALOG}
        assert ProjectRoleRules.assignable_keys() <= catalog
        assert len(ProjectRoleRules.assignable_keys()) == 38

    def test_no_catalog_atom_is_unreachable(self) -> None:
        """A scoped atom is withheld from every global role by seed_rbac, so
        if ASSIGNABLE also excludes it no role can ever hold it and its route
        is dead for everyone."""
        assignable = ProjectRoleRules.assignable_keys()
        unreachable = [
            (resource, action)
            for resource, action, _ in RbacPermissionCatalog.CATALOG
            if RbacScoping.is_scoped(resource) and (resource, action) not in assignable
        ]
        assert unreachable == []


class TestRejectsUnassignable:
    def test_accepts_every_assignable_key(self) -> None:
        assert ProjectRoleRules.rejects_unassignable([("environment", "update"), ("project", "read")]) == []

    def test_rejects_user_update_status(self) -> None:
        keys = [("environment", "update"), ("user", "update_status")]
        assert ProjectRoleRules.rejects_unassignable(keys) == [("user", "update_status")]

    def test_rejects_project_delete(self) -> None:
        assert ProjectRoleRules.rejects_unassignable([("project", "delete")]) == [("project", "delete")]


class TestEffectivePermissions:
    def test_null_project_role_yields_exactly_the_global_set(self) -> None:
        global_keys = frozenset({"project.read", "environment.read"})
        assert ProjectRoleRules.effective_permissions(global_keys, frozenset()) == global_keys

    def test_project_role_adds_to_global_not_replaces_it(self) -> None:
        global_keys = frozenset({"project.read"})
        project_keys = frozenset({"environment.update"})
        result = ProjectRoleRules.effective_permissions(global_keys, project_keys)
        assert result == frozenset({"project.read", "environment.update"})

    def test_overlapping_keys_do_not_duplicate(self) -> None:
        global_keys = frozenset({"environment.read"})
        project_keys = frozenset({"environment.read"})
        result = ProjectRoleRules.effective_permissions(global_keys, project_keys)
        assert result == frozenset({"environment.read"})

    def test_manage_all_adds_the_scoped_surface_minus_the_account_tier(self) -> None:
        global_keys = frozenset({"project.manage_all"})
        result = ProjectRoleRules.effective_permissions(global_keys, frozenset(), manages_all_projects=True)
        assert RbacScoping.manage_all_permission_keys() <= result
        assert "project.manage_all" in result

    def test_manage_all_views_the_cloudflare_tier_but_never_writes_it(self) -> None:
        """Global grant admits viewing; a write would satisfy
        require_cloudflare_environment_access's project-role fallback and
        mutate an account nobody granted this operator."""
        result = ProjectRoleRules.effective_permissions(frozenset(), frozenset(), manages_all_projects=True)
        for key in (
            "environment_cloudflare_traffic.read",
            "project_cloudflare_config.read",
            "project_cloudflare_tunnel.read",
        ):
            assert key in result
        for key in (
            "project_cloudflare_tunnel.create",
            "project_cloudflare_tunnel.sync",
            "project_cloudflare_dns.delete",
            "project_cloudflare_hostname.update",
        ):
            assert key not in result

    def test_a_project_role_can_still_grant_the_cloudflare_twins(self) -> None:
        """The legitimate path stays open: a project role still grants them,
        scoped to that one project."""
        project_keys = frozenset({"project_cloudflare_tunnel.create"})
        result = ProjectRoleRules.effective_permissions(frozenset(), project_keys, manages_all_projects=True)
        assert "project_cloudflare_tunnel.create" in result

    def test_manage_all_covers_the_atoms_the_403_reports_named(self) -> None:
        """The routes an operator actually hit: notification channels,
        alerting, incidents, Loki."""
        result = ProjectRoleRules.effective_permissions(frozenset(), frozenset(), manages_all_projects=True)
        for key in (
            "project_notification_channel.read",
            "project_notification_channel.create",
            "project_alert_rule.read",
            "project_incident.read",
            "project_loki_config.read",
        ):
            assert key in result

    def test_default_is_unchanged_union_when_flag_absent(self) -> None:
        """The flag is opt-in: two-positional-arg callers keep their old
        result byte for byte."""
        global_keys = frozenset({"project.read"})
        project_keys = frozenset({"environment.update"})
        assert ProjectRoleRules.effective_permissions(global_keys, project_keys) == (
            global_keys | project_keys
        )
        assert not (
            RbacScoping.scoped_permission_keys()
            & ProjectRoleRules.effective_permissions(global_keys, project_keys)
        )
