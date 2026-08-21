/**
 * Hierarchical query key factory for the project entity.
 */
export const projectsKeys = {
  all: ["projects"] as const,
  lists: () => [...projectsKeys.all, "list"] as const,
  list: (filters?: { limit?: number; offset?: number }) =>
    [...projectsKeys.lists(), filters] as const,
  detail: (id: string) => [...projectsKeys.all, "detail", id] as const,
};
