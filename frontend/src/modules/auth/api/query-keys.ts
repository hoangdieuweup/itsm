/**
 * Hierarchical query key factory for the auth module — never inline
 * `["auth", "session"]` string arrays in components, always go through this
 * so `invalidateQueries`/`removeQueries` targeting stays correct if the
 * shape changes (see nextjs-modular-architecture/references/data-layer.md).
 */
export const authKeys = {
  all: ["auth"] as const,
  session: () => [...authKeys.all, "session"] as const,
};
