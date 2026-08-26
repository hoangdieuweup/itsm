"""Unit tests for app.modules.rbac.constants — the fixed permission catalog."""

from app.modules.rbac.constants import RbacPermissionCatalog


class TestRbacPermissionCatalog:
    def test_catalog_includes_alert_rule_and_incident_permissions(self) -> None:
        resources_actions = {(r, a) for r, a, _ in RbacPermissionCatalog.CATALOG}
        assert ("project", "manage_all") in resources_actions
        assert ("project_role", "read") in resources_actions
        assert ("project_role", "manage") in resources_actions
        assert len(RbacPermissionCatalog.CATALOG) == 81

    def test_project_scoped_resources_are_distinct_names_not_aliases(self) -> None:
        """The project surface must never be checkable under an account-level
        resource string — that aliasing IS the escalation bug this splits."""
        resources_actions = {(r, a) for r, a, _ in RbacPermissionCatalog.CATALOG}
        for action in ("read", "create", "sync", "refresh_status"):
            assert ("project_cloudflare_tunnel", action) in resources_actions
        for action in ("read", "create", "update", "delete"):
            assert ("project_cloudflare_hostname", action) in resources_actions
            assert ("project_cloudflare_dns", action) in resources_actions
            assert ("project_alert_rule", action) in resources_actions
        assert ("project_cloudflare_config", "read") in resources_actions
        assert ("project_cloudflare_audit", "read") in resources_actions
        for action in ("read", "manage"):
            assert ("project_loki_config", action) in resources_actions
        for action in ("create", "read", "acknowledge", "resolve"):
            assert ("project_incident", action) in resources_actions

    def test_dangerous_tunnel_atoms_have_no_project_scoped_twin(self) -> None:
        resources_actions = {(r, a) for r, a, _ in RbacPermissionCatalog.CATALOG}
        assert ("cloudflare_tunnel", "delete") in resources_actions
        assert ("cloudflare_tunnel", "reveal_token") in resources_actions
        assert ("project_cloudflare_tunnel", "delete") not in resources_actions
        assert ("project_cloudflare_tunnel", "reveal_token") not in resources_actions

    def test_retires_resources_whose_only_call_sites_became_project_scoped(self) -> None:
        resources_actions = {(r, a) for r, a, _ in RbacPermissionCatalog.CATALOG}
        assert ("loki_config", "read") not in resources_actions
        assert ("loki_config", "manage") not in resources_actions
        for action in ("create", "update", "delete"):
            assert ("alert_rule", action) not in resources_actions
        for action in ("create", "acknowledge", "resolve"):
            assert ("incident", action) not in resources_actions
        # Retained: each still guards one genuinely account/global-level route.
        assert ("alert_rule", "read") in resources_actions
        assert ("incident", "read") in resources_actions
        assert ("cloudflare_config", "read") in resources_actions

    def test_description_key_always_embeds_its_own_resource(self) -> None:
        for resource, action, description_key in RbacPermissionCatalog.CATALOG:
            assert description_key == f"permissions.{resource}.{action}"
