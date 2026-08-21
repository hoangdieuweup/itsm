/**
 * Hierarchical query key factory for the environment entity.
 */
export const environmentsKeys = {
  all: ["environments"] as const,
  forProject: (projectId: string) => [...environmentsKeys.all, "project", projectId] as const,
  detail: (id: string) => [...environmentsKeys.all, "detail", id] as const,
};
