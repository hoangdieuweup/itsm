"""Unit tests for app.modules.rbac.constants — the fixed permission catalog."""

from app.modules.rbac.constants import RbacPermissionCatalog, RbacScoping


class TestRbacPermissionCatalog:
    def test_catalog_includes_alert_rule_and_incident_permissions(self) -> None:
        resources_actions = {(r, a) for r, a, _ in RbacPermissionCatalog.CATALOG}
        assert ("project", "manage_all") in resources_actions
        assert ("project_role", "read") in resources_actions
        assert ("project_role", "manage") in resources_actions
        assert len(RbacPermissionCatalog.CATALOG) == 80

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
        assert ("environment_cloudflare_traffic", "read") in resources_actions
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
        for action in ("create", "read", "update", "delete"):
            assert ("alert_rule", action) not in resources_actions
        for action in ("create", "acknowledge", "resolve"):
            assert ("incident", action) not in resources_actions
        for action in ("create", "read", "update", "delete", "test_send"):
            assert ("notification_channel", action) not in resources_actions
        # Retained: each still guards one genuinely account/global-level route.
        assert ("incident", "read") in resources_actions
        assert ("cloudflare_config", "read") in resources_actions
        assert ("cloudflare_traffic", "read") not in resources_actions
        assert ("environment_cloudflare_traffic", "read") in resources_actions

    def test_description_key_always_embeds_its_own_resource(self) -> None:
        for resource, action, description_key in RbacPermissionCatalog.CATALOG:
            assert description_key == f"permissions.{resource}.{action}"


class TestRbacScoping:
    def test_project_scoped_twins_are_scoped(self) -> None:
        """Every twin the split created is satisfied through a project role
        only — a global grant would reach projects the holder isn't in."""
        for resource in (
            "project_cloudflare_config",
            "project_cloudflare_dns",
            "project_cloudflare_tunnel",
            "project_cloudflare_hostname",
            "project_loki_config",
            "project_alert_rule",
            "project_incident",
            "project_notification_channel",
            "environment_cloudflare_traffic",
        ):
            assert RbacScoping.is_scoped(resource)

    def test_project_administration_resources_stay_globally_grantable(self) -> None:
        """These only SHARE the prefix; a bare startswith test swallowing
        them is what stripped them off the admin role."""
        for resource in ("project_member", "project_link", "project_role"):
            assert not RbacScoping.is_scoped(resource)

    def test_unprefixed_resources_are_never_scoped(self) -> None:
        """`project` and `environment` are the parent resources, not twins —
        the trailing underscore is load-bearing."""
        for resource in ("project", "environment", "role", "user", "cloudflare_tunnel", "incident"):
            assert not RbacScoping.is_scoped(resource)

    def test_every_exempted_resource_actually_exists_in_the_catalog(self) -> None:
        """An exemption for a resource nothing defines is a dead entry that
        silently stops protecting the moment the real name drifts."""
        resources = {r for r, _, _ in RbacPermissionCatalog.CATALOG}
        assert RbacScoping.PROJECT_ADMINISTRATION_RESOURCES <= resources

    def test_only_the_cloudflare_twins_are_account_tiered(self) -> None:
        assert RbacScoping.is_account_tiered("project_cloudflare_tunnel")
        assert RbacScoping.is_account_tiered("project_cloudflare_dns")
        assert RbacScoping.is_account_tiered("project_cloudflare_hostname")
        assert RbacScoping.is_account_tiered("project_cloudflare_config")
        assert RbacScoping.is_account_tiered("environment_cloudflare_traffic")
        assert not RbacScoping.is_account_tiered("project_notification_channel")
        assert not RbacScoping.is_account_tiered("project_alert_rule")
        assert not RbacScoping.is_account_tiered("project_incident")
        assert not RbacScoping.is_account_tiered("project_loki_config")

    def test_manage_all_withholds_only_account_tiered_writes(self) -> None:
        scoped = RbacScoping.scoped_permission_keys()
        manage_all = RbacScoping.manage_all_permission_keys()
        assert manage_all < scoped
        for key in scoped - manage_all:
            resource, action = key.split(".", 1)
            assert RbacScoping.is_account_tiered(resource)
            assert action != "read"

    def test_manage_all_can_view_every_account_tiered_resource(self) -> None:
        """Viewing across projects must not require an account-manager grant."""
        manage_all = RbacScoping.manage_all_permission_keys()
        for key in (
            "environment_cloudflare_traffic.read",
            "project_cloudflare_config.read",
            "project_cloudflare_tunnel.read",
            "project_cloudflare_dns.read",
            "project_cloudflare_hostname.read",
        ):
            assert key in manage_all

    def test_manage_all_cannot_write_an_account_tiered_resource(self) -> None:
        manage_all = RbacScoping.manage_all_permission_keys()
        for key in (
            "project_cloudflare_tunnel.create",
            "project_cloudflare_tunnel.sync",
            "project_cloudflare_tunnel.refresh_status",
            "project_cloudflare_dns.create",
            "project_cloudflare_dns.update",
            "project_cloudflare_dns.delete",
            "project_cloudflare_hostname.create",
            "project_cloudflare_hostname.update",
            "project_cloudflare_hostname.delete",
        ):
            assert key not in manage_all

    def test_manage_all_set_still_covers_the_operational_twins(self) -> None:
        manage_all = RbacScoping.manage_all_permission_keys()
        for key in (
            "project_notification_channel.read",
            "project_notification_channel.test_send",
            "project_alert_rule.create",
            "project_incident.acknowledge",
            "project_loki_config.manage",
        ):
            assert key in manage_all
