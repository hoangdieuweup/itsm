/**
 * Hierarchical query key factory for the project-links sub-resource.
 * Never inline query key strings — always use this factory.
 */
export const projectLinksKeys = {
  all: ["projects", "links"] as const,
  forProject: (projectId: string) => [...projectLinksKeys.all, projectId] as const,
};
