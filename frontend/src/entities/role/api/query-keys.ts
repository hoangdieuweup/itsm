/**
 * Hierarchical query key factory for the role entity.
 */
export const rolesKeys = {
  all: ["roles"] as const,
  lists: () => [...rolesKeys.all, "list"] as const,
  list: (filters?: { limit?: number; offset?: number }) =>
    [...rolesKeys.lists(), filters] as const,
  detail: (id: string) => [...rolesKeys.all, "detail", id] as const,
  userRoles: (userId: string) => [...rolesKeys.all, "user", userId] as const,
  permissions: () => ["rbac", "permissions"] as const,
};
