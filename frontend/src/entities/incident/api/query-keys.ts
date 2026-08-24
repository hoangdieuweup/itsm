export const incidentsKeys = {
  all: ["incidents"] as const,
  list: (filters: { projectId?: string; environmentId?: string; status?: string }) =>
    [...incidentsKeys.all, "list", filters] as const,
  detail: (id: string) => [...incidentsKeys.all, "detail", id] as const,
};
