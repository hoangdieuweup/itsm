"use client";

import type { ReactNode } from "react";
import { ACCOUNT_TIER_TWIN, type Resource } from "@/shared/constants/permissions";
import { useCan } from "../model/permission-context";
import { useCanInProject } from "../model/project-permission-context";

/**
 * True when the caller holds the project-scoped resource inside this
 * project, OR its account-level twin globally — the same either/or
 * `require_cloudflare_environment_access` enforces.
 *
 * The global half is necessary but not sufficient server-side: that path
 * also requires a cloudflare_account_managers grant, which the frontend
 * cannot see. So this can show a control that 403s for a global-atom
 * holder who manages no account. Hiding it from real account managers —
 * the alternative — was the worse failure.
 */
export function useCanInProjectOrAccount(projectResource: Resource, action: string): boolean {
  const allowedInProject = useCanInProject(projectResource, action);
  const allowedOnAccount = useCan(ACCOUNT_TIER_TWIN[projectResource] ?? "", action);
  return allowedInProject || allowedOnAccount;
}

export function CanInProjectOrAccount({
  I: action,
  a: resource,
  children,
  fallback = null,
}: {
  I: string;
  a: Resource;
  children: ReactNode | ((state: { isAllowed: boolean }) => ReactNode);
  fallback?: ReactNode;
}) {
  const isAllowed = useCanInProjectOrAccount(resource, action);
  if (typeof children === "function") return <>{children({ isAllowed })}</>;
  return <>{isAllowed ? children : fallback}</>;
}
