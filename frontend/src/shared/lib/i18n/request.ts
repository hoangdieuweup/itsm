import { getRequestConfig } from "next-intl/server";
import { hasLocale } from "next-intl";
import { routing } from "./routing";

export default getRequestConfig(async ({ requestLocale }) => {
  const requested = await requestLocale;
  const locale = hasLocale(routing.locales, requested)
    ? requested
    : routing.defaultLocale;

  const [
    common,
    auth,
    users,
    roles,
    projects,
    auditLog,
    cloudflareAccounts,
    cloudflareDns,
    cloudflareTunnels,
    logViewer,
    notifications,
    alerting,
    incidents,
  ] = await Promise.all([
    import(`../../../../locales/${locale}/common.json`),
    import(`../../../../locales/${locale}/modules/auth.json`),
    import(`../../../../locales/${locale}/modules/users.json`),
    import(`../../../../locales/${locale}/modules/roles.json`),
    import(`../../../../locales/${locale}/modules/projects.json`),
    import(`../../../../locales/${locale}/modules/audit-log.json`),
    import(`../../../../locales/${locale}/modules/cloudflare-accounts.json`),
    import(`../../../../locales/${locale}/modules/cloudflare-dns.json`),
    import(`../../../../locales/${locale}/modules/cloudflare-tunnels.json`),
    import(`../../../../locales/${locale}/modules/log-viewer.json`),
    import(`../../../../locales/${locale}/modules/notifications.json`),
    import(`../../../../locales/${locale}/modules/alerting.json`),
    import(`../../../../locales/${locale}/modules/incidents.json`),
  ]);

  return {
    locale,
    messages: {
      common: common.default,
      auth: auth.default,
      users: users.default,
      roles: roles.default,
      projects: projects.default,
      auditLog: auditLog.default,
      cloudflareAccounts: cloudflareAccounts.default,
      cloudflareDns: cloudflareDns.default,
      cloudflareTunnels: cloudflareTunnels.default,
      logViewer: logViewer.default,
      notifications: notifications.default,
      alerting: alerting.default,
      incidents: incidents.default,
    },
  };
});
