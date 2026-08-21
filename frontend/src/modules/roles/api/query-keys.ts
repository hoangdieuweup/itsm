/**
 * Hierarchical query key factory for the roles/rbac module.
 */
export const rolesKeys = {
  all: ["roles"] as const,
  lists: () => [...rolesKeys.all, "list"] as const,
  list: (filters?: { limit?: number; offset?: number }) =>
    [...rolesKeys.lists(), filters] as const,
  detail: (id: number) => [...rolesKeys.all, "detail", id] as const,
  permissions: () => ["rbac", "permissions"] as const,
};
