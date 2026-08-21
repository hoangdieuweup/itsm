/**
 * Hierarchical query key factory for the users module.
 * Never inline query key strings — always use this factory.
 */
export const usersKeys = {
  all: ["users"] as const,
  lists: () => [...usersKeys.all, "list"] as const,
  list: (filters?: { limit?: number; offset?: number }) =>
    [...usersKeys.lists(), filters] as const,
  detail: (id: number) => [...usersKeys.all, "detail", id] as const,
};
