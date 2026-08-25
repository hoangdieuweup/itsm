"""Unit tests for app.modules.rbac.constants — the fixed permission catalog."""

from app.modules.rbac.constants import RbacPermissionCatalog


class TestRbacPermissionCatalog:
    def test_catalog_includes_alert_rule_and_incident_permissions(self) -> None:
        resources_actions = {(r, a) for r, a, _ in RbacPermissionCatalog.CATALOG}
        for action in ("create", "read", "update", "delete"):
            assert ("alert_rule", action) in resources_actions
        for action in ("create", "read", "acknowledge", "resolve"):
            assert ("incident", action) in resources_actions
        assert ("incident", "update") not in resources_actions
        assert ("incident", "delete") not in resources_actions
        assert ("project", "manage_all") in resources_actions
        assert ("project_role", "read") in resources_actions
        assert ("project_role", "manage") in resources_actions
        assert len(RbacPermissionCatalog.CATALOG) == 65
