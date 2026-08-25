export const projectPermissionsKeys = {
  all: ["permissions", "project"] as const,
  forProject: (projectId: string) => [...projectPermissionsKeys.all, projectId] as const,
};
