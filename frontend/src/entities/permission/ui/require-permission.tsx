"use client";

import type { ReactNode } from "react";
import { useCan } from "../model/permission-context";

/**
 * Page-level permission guard. Renders `fallback` (e.g. a "no access" page)
 * when the user lacks the required permission.
 *
 * Still UX only — for a real boundary, also check on the server in the
 * page's Server Component before any prefetch runs. This client-side guard
 * avoids a flash of content before the redirect resolves, or handles the
 * case where a permission is revoked mid-session.
 */
export function RequirePermission({
  resource,
  action,
  children,
  fallback,
}: {
  resource: string;
  action: string;
  children: ReactNode;
  fallback: ReactNode;
}) {
  const isAllowed = useCan(resource, action);
  return <>{isAllowed ? children : fallback}</>;
}
