/**
 * Hierarchical query key factory for the auth session — never inline
 * `["auth", "session"]` string arrays in components, always go through this
 * so `invalidateQueries`/`removeQueries` targeting stays correct if the
 * shape changes (see nextjs-modular-architecture/references/data-layer.md).
 *
 * Lives in entities/, not modules/auth/, so any module can invalidate the
 * session after a mutation that changes what it reflects (role/permission
 * changes) without a forbidden module-to-module import.
 */
export const authKeys = {
  all: ["auth"] as const,
  session: () => [...authKeys.all, "session"] as const,
};
