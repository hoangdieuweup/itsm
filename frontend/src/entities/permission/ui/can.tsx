"use client";

import type { ReactNode } from "react";
import { useCan } from "../model/permission-context";

interface CanProps {
  /** The action to check, e.g. "delete", "read", "update_status" */
  I: string;
  /** The resource to check, e.g. "user", "role" */
  a: string;
  /** Element to render when allowed, or a render function receiving { isAllowed } */
  children: ReactNode | ((state: { isAllowed: boolean }) => ReactNode);
  /** Element to render when NOT allowed (default: null = hidden) */
  fallback?: ReactNode;
}

/**
 * Permission gate for individual UI elements. UX only — the backend's
 * `require_permission` is the real enforcement.
 *
 * Hide pattern (nav items, whole sections):
 *   <Can I="delete" a="user"><DeleteButton /></Can>
 *
 * Disable pattern (toolbar buttons where removal breaks layout):
 *   <Can I="delete" a="user">
 *     {({ isAllowed }) => <Button disabled={!isAllowed}>Delete</Button>}
 *   </Can>
 */
export function Can({ I: action, a: resource, children, fallback = null }: CanProps) {
  const isAllowed = useCan(resource, action);
  if (typeof children === "function") return <>{children({ isAllowed })}</>;
  return <>{isAllowed ? children : fallback}</>;
}
