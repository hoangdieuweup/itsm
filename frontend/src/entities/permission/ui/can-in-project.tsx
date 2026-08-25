"use client";

import type { ReactNode } from "react";

import { useCanInProject } from "../model/project-permission-context";

interface CanInProjectProps {
  /** The action to check, e.g. "update", "read" */
  I: string;
  /** The resource to check, e.g. "environment", "project_link" */
  a: string;
  /** Element to render when allowed, or a render function receiving { isAllowed } */
  children: ReactNode | ((state: { isAllowed: boolean }) => ReactNode);
  /** Element to render when NOT allowed (default: null = hidden) */
  fallback?: ReactNode;
}

/**
 * Project-scoped permission gate — mirrors <Can> but checks the caller's
 * EFFECTIVE set for one project (global permissions unioned with any
 * project role grant), not just the global set. UX only — the backend's
 * require_project_permission dependency is the real enforcement.
 *
 * Must be rendered under a <ProjectPermissionProvider projectId="...">.
 */
export function CanInProject({ I: action, a: resource, children, fallback = null }: CanInProjectProps) {
  const isAllowed = useCanInProject(resource, action);
  if (typeof children === "function") return <>{children({ isAllowed })}</>;
  return <>{isAllowed ? children : fallback}</>;
}
