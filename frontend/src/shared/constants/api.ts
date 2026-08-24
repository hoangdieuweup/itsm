const RAW_API_URL = process.env.NEXT_PUBLIC_API_URL?.replace(/\/+$/, "") ?? "";
const API_V1_PREFIX = "/api/v1";

export const API_CONFIG = {
  BASE_URL: RAW_API_URL,
  API_V1_URL: RAW_API_URL ? `${RAW_API_URL}${API_V1_PREFIX}` : API_V1_PREFIX,
  ENDPOINTS: {
    AUTH: {
      SSO_START: `${RAW_API_URL ? `${RAW_API_URL}${API_V1_PREFIX}` : API_V1_PREFIX}/auth/oauth/dx/start`,
      ME: "/auth/me",
      REFRESH: "/auth/refresh",
      LOGOUT: "/auth/logout",
    },
    USERS: {
      ROOT: "/users",
      STATUS: (id: string) => `/users/${id}/status`,
    },
    RBAC: {
      ROLES: "/rbac/roles",
      ROLE_DETAIL: (id: string) => `/rbac/roles/${id}`,
      PERMISSIONS: "/rbac/permissions",
      USER_ROLE: (userId: string) => `/rbac/users/${userId}/role`,
      USER_ROLES: (userId: string) => `/rbac/users/${userId}/roles`,
    },
    PROJECTS: {
      ROOT: "/projects",
      DETAIL: (id: string) => `/projects/${id}`,
      ENVIRONMENTS: (projectId: string) => `/projects/${projectId}/environments`,
      ENVIRONMENT_DETAIL: (id: string) => `/environments/${id}`,
      LINKS: (projectId: string) => `/projects/${projectId}/links`,
      LINK_DETAIL: (id: string) => `/links/${id}`,
    },
    AUDIT_LOGS: {
      ROOT: "/audit-logs",
    },
    CLOUDFLARE_ACCOUNTS: {
      ROOT: "/cloudflare-accounts",
      DETAIL: (id: string) => `/cloudflare-accounts/${id}`,
      TEST_CONNECTION: (id: string) => `/cloudflare-accounts/${id}/test-connection`,
      REVEAL_TOKEN: (id: string) => `/cloudflare-accounts/${id}/reveal-token`,
      MANAGERS: (id: string) => `/cloudflare-accounts/${id}/managers`,
      MANAGER_DETAIL: (id: string, userId: string) => `/cloudflare-accounts/${id}/managers/${userId}`,
    },
    CLOUDFLARE_DNS: {
      ZONES: (accountId: string) => `/cloudflare-accounts/${accountId}/zones`,
      CONFIGS_ROOT: "/cloudflare-configs",
      CONFIG: (environmentId: string) => `/environments/${environmentId}/cloudflare-config`,
      RECORDS: (environmentId: string) => `/environments/${environmentId}/dns-records`,
      RECORD_DETAIL: (environmentId: string, recordId: string) =>
        `/environments/${environmentId}/dns-records/${recordId}`,
      SYNC: (environmentId: string) => `/environments/${environmentId}/dns-records/sync`,
    },
    CLOUDFLARE_TUNNELS: {
      ROOT: (environmentId: string) => `/environments/${environmentId}/cloudflare-tunnels`,
      SYNC: (environmentId: string) => `/environments/${environmentId}/cloudflare-tunnels/sync`,
      DETAIL: (environmentId: string, tunnelId: string) =>
        `/environments/${environmentId}/cloudflare-tunnels/${tunnelId}`,
      REVEAL_TOKEN: (environmentId: string, tunnelId: string) =>
        `/environments/${environmentId}/cloudflare-tunnels/${tunnelId}/reveal-token`,
      REFRESH_STATUS: (environmentId: string, tunnelId: string) =>
        `/environments/${environmentId}/cloudflare-tunnels/${tunnelId}/refresh-status`,
      HOSTNAMES: (environmentId: string, tunnelId: string) =>
        `/environments/${environmentId}/cloudflare-tunnels/${tunnelId}/hostnames`,
      HOSTNAME_DETAIL: (environmentId: string, tunnelId: string, hostnameId: string) =>
        `/environments/${environmentId}/cloudflare-tunnels/${tunnelId}/hostnames/${hostnameId}`,
    },
    CLOUDFLARE_AUDIT_LOGS: {
      ROOT: (environmentId: string) => `/environments/${environmentId}/cloudflare-audit-logs`,
    },
    OBSERVABILITY: {
      LOKI_CONFIG: (environmentId: string) => `/environments/${environmentId}/loki-config`,
      LOKI_QUERY: (environmentId: string) => `/environments/${environmentId}/loki-config/query`,
      LOKI_TAIL: (environmentId: string) => `/environments/${environmentId}/loki-config/tail`,
    },
    NOTIFICATION_CHANNELS: {
      ROOT: "/notification-channels",
      DETAIL: (id: string) => `/notification-channels/${id}`,
      TEST_SEND: (id: string) => `/notification-channels/${id}/test-send`,
    },
    ALERT_RULES: {
      AVAILABLE_ALERTS: (accountId: string) => `/cloudflare-accounts/${accountId}/available-alerts`,
      ROOT: (environmentId: string) => `/environments/${environmentId}/alert-rules`,
      DETAIL: (alertRuleId: string) => `/alert-rules/${alertRuleId}`,
    },
    INCIDENTS: {
      ROOT: "/incidents",
      DETAIL: (id: string) => `/incidents/${id}`,
      ACKNOWLEDGE: (id: string) => `/incidents/${id}/acknowledge`,
      RESOLVE: (id: string) => `/incidents/${id}/resolve`,
    },
  },
} as const;
