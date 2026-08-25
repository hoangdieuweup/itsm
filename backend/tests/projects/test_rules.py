"""Unit tests for app.modules.projects.rules — pure decisions, no I/O."""

from app.modules.projects.rules import ProjectRoleRules


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

    def test_includes_environment_scoped_cloudflare_loki_alerting_atoms(self) -> None:
        keys = ProjectRoleRules.assignable_keys()
        assert ("cloudflare_dns", "create") in keys
        assert ("cloudflare_tunnel", "create") in keys
        assert ("cloudflare_tunnel", "reveal_token") in keys
        assert ("cloudflare_hostname", "update") in keys
        assert ("cloudflare_config", "read") in keys
        assert ("cloudflare_audit", "read") in keys
        assert ("loki_config", "manage") in keys
        assert ("alert_rule", "create") in keys
        assert ("incident", "acknowledge") in keys

    def test_excludes_cloudflare_account_administration_and_binding(self) -> None:
        keys = ProjectRoleRules.assignable_keys()
        assert ("cloudflare_account", "create") not in keys
        assert ("cloudflare_account", "delete") not in keys
        assert ("cloudflare_account", "reveal_token") not in keys
        assert ("cloudflare_account", "manage_all") not in keys
        assert ("cloudflare_manager", "read") not in keys
        assert ("cloudflare_manager", "manage") not in keys
        assert ("cloudflare_config", "manage") not in keys


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
