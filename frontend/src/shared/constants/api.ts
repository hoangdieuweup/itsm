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
  },
} as const;
