/**
 * Hierarchical query key factory for the project-links sub-resource.
 * Never inline query key strings — always use this factory.
 */
export const projectLinksKeys = {
  all: ["projects", "links"] as const,
  forProject: (projectId: string) => [...projectLinksKeys.all, projectId] as const,
};

export const projectMembersKeys = {
  all: ["projects", "members"] as const,
  forProject: (projectId: string) => [...projectMembersKeys.all, projectId] as const,
};

export const projectRolesKeys = {
  all: ["projects", "roles"] as const,
  forProject: (projectId: string) => [...projectRolesKeys.all, projectId] as const,
};

export const assignablePermissionsKeys = {
  all: ["projects", "assignable-permissions"] as const,
};
