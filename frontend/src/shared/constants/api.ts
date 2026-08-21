const RAW_API_URL = process.env.NEXT_PUBLIC_API_URL?.replace(/\/+$/, "") ?? "";
const API_V1_PREFIX = "/api/v1";

export const API_CONFIG = {
  BASE_URL: RAW_API_URL,
  API_V1_URL: RAW_API_URL ? `${RAW_API_URL}${API_V1_PREFIX}` : API_V1_PREFIX,
  ENDPOINTS: {
    AUTH: {
      SSO_START: `${RAW_API_URL ? `${RAW_API_URL}${API_V1_PREFIX}` : API_V1_PREFIX}/auth/oauth/dx/start`,
      ME: "/auth/me",
      LOGOUT: "/auth/logout",
    },
    USERS: {
      ROOT: "/users",
      STATUS: (id: number) => `/users/${id}/status`,
    },
    RBAC: {
      ROLES: "/rbac/roles",
      ROLE_DETAIL: (id: number) => `/rbac/roles/${id}`,
      PERMISSIONS: "/rbac/permissions",
      USER_ROLE: (userId: number) => `/rbac/users/${userId}/role`,
    },
  },
} as const;
