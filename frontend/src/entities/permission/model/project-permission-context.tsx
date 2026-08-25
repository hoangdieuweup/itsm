"use client";

import { createContext, useCallback, useContext, useMemo, type ReactNode } from "react";

import { useProjectPermissionsQuery } from "../hooks/use-project-permissions";
import { GlobalCanContext } from "./permission-context";

interface ProjectPermissionContextValue {
  can: (resource: string, action: string) => boolean;
}

const ProjectPermissionContext = createContext<ProjectPermissionContextValue | null>(null);

/**
 * Seeds the project-scoped permission set for CanInProject/useCanInProject
 * inside one project's UI tree. D8: while the query is pending or on
 * error, falls back to the outer GLOBAL useCan — the effective set is
 * always a superset of global, so this can only ever under-grant during
 * the fallback window, never over-grant, never flicker a control off.
 */
export function ProjectPermissionProvider({
  projectId,
  children,
}: {
  projectId: string;
  children: ReactNode;
}) {
  const { data, isPending, isError } = useProjectPermissionsQuery(projectId);
  const globalCan = useContext(GlobalCanContext);

  const permissionSet = useMemo(() => new Set(data ?? []), [data]);
  const can = useCallback(
    (resource: string, action: string) => {
      if (isPending || isError) return globalCan(resource, action);
      return permissionSet.has(`${resource}.${action}`);
    },
    [isPending, isError, globalCan, permissionSet],
  );
  const value = useMemo(() => ({ can }), [can]);

  return <ProjectPermissionContext.Provider value={value}>{children}</ProjectPermissionContext.Provider>;
}

export function useCanInProject(resource: string, action: string): boolean {
  const ctx = useContext(ProjectPermissionContext);
  if (ctx === null) throw new Error("useCanInProject must be used within a ProjectPermissionProvider");
  return ctx.can(resource, action);
}
