"use client";

import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  type ReactNode,
} from "react";

import type { Permission } from "../lib/permission";

export type { Permission };


interface PermissionContextValue {
  permissions: ReadonlySet<Permission>;
  can: (resource: string, action: string) => boolean;
}

const PermissionContext = createContext<PermissionContextValue | null>(null);

/**
 * Just the `can` function, re-provided alongside PermissionContext so
 * project-scoped permission contexts (see project-permission-context.tsx)
 * can fall back to the global permission set without re-implementing
 * useCan's per-(resource,action) hook signature.
 */
export const GlobalCanContext = createContext<(resource: string, action: string) => boolean>(
  () => false,
);

/**
 * Seeds the permission set for every downstream `<Can>`, `useCan`, and
 * `<RequirePermission>` in the dashboard tree. Wired once in AuthGuard,
 * seeded from the server-verified session's `permissions` array — never
 * from a client-editable source like a URL param or localStorage.
 *
 * This is UX only. The backend's `require_permission` dependency is the
 * real enforcement — see references/rbac-ui.md.
 */
export function PermissionProvider({
  permissions,
  children,
}: {
  permissions: Permission[];
  children: ReactNode;
}) {
  const permissionSet = useMemo(() => new Set(permissions), [permissions]);
  const can = useCallback(
    (resource: string, action: string) =>
      permissionSet.has(`${resource}.${action}` as Permission),
    [permissionSet],
  );
  const value = useMemo(
    () => ({ permissions: permissionSet, can }),
    [permissionSet, can],
  );

  return (
    <PermissionContext.Provider value={value}>
      <GlobalCanContext.Provider value={can}>{children}</GlobalCanContext.Provider>
    </PermissionContext.Provider>
  );
}

/**
 * Check a single permission. Throws if called outside PermissionProvider.
 */
export function useCan(resource: string, action: string): boolean {
  const ctx = useContext(PermissionContext);
  if (ctx === null)
    throw new Error("useCan must be used within a PermissionProvider");
  return ctx.can(resource, action);
}
