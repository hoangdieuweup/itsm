# Permission-gated UI (RBAC)

Mirrors the backend's contract exactly (see `fastapi-modular-scaffold`'s `references/rbac.md`): permissions are `resource.action` strings, scoped to one organization, never a hardcoded role name. Only applies when that backend contract exists — read the backend's rules before building this, don't invent a different shape.

## The one rule that matters: this is UX, not security

Hiding or disabling a button does not protect anything — it only avoids showing UI for an action that would fail anyway. The backend's `require_permission` dependency is the only real enforcement; every check described here can be bypassed by calling the API directly, and that's fine, because the API is what actually guards the data. Never reason "we hid the delete button, so it's safe" — reason "the API 403s on delete, so hiding the button is just a nicer experience."

## PermissionProvider

One provider, wired once, alongside `QueryClientProvider`/`MotionProvider`:

```tsx
// entities/permission/model/permission-context.tsx
"use client";

import { createContext, useCallback, useContext, useMemo, type ReactNode } from "react";

export type Permission = `${string}.${string}`;

interface PermissionContextValue {
  organizationId: string;
  permissions: ReadonlySet<Permission>;
  can: (resource: string, action: string) => boolean;
}

const PermissionContext = createContext<PermissionContextValue | null>(null);

export function PermissionProvider({
  organizationId,
  permissions,
  children,
}: {
  organizationId: string;
  permissions: Permission[];
  children: ReactNode;
}) {
  const permissionSet = useMemo(() => new Set(permissions), [permissions]);
  const can = useCallback(
    (resource: string, action: string) => permissionSet.has(`${resource}.${action}` as Permission),
    [permissionSet]
  );
  const value = useMemo(() => ({ organizationId, permissions: permissionSet, can }), [organizationId, permissionSet, can]);

  return <PermissionContext.Provider value={value}>{children}</PermissionContext.Provider>;
}

export function useCan(resource: string, action: string): boolean {
  const ctx = useContext(PermissionContext);
  if (ctx === null) throw new Error("useCan must be used within a PermissionProvider");
  return ctx.can(resource, action);
}
```

`organizationId` and `permissions` come from the server-verified session (a Server Component reading the session cookie, prefetched the same way any other data is — see `references/data-layer.md`), **never** from a client-editable source like a URL param or `localStorage`. The multi-tenant permission bug that actually happens in production is a request handler trusting a client-supplied org id instead of the one bound to the session; the same discipline applies here — the org id the provider is seeded with must come from the same place the backend trusts.

## `<Can>` — buttons, modals, any single element

```tsx
// entities/permission/ui/can.tsx
"use client";

import type { ReactNode } from "react";
import { useCan } from "@/entities/permission";

interface CanProps {
  I: string; // action
  a: string; // resource
  children: ReactNode | ((state: { isAllowed: boolean }) => ReactNode);
  fallback?: ReactNode;
}

export function Can({ I: action, a: resource, children, fallback = null }: CanProps) {
  const isAllowed = useCan(resource, action);
  if (typeof children === "function") return <>{children({ isAllowed })}</>;
  return <>{isAllowed ? children : fallback}</>;
}
```

**Hide** — for nav items, whole sections, anything where removing it entirely doesn't break layout:
```tsx
<Can I="delete" a="members">
  <DeleteButton />
</Can>
```

**Disable** — for an action button that's part of a fixed toolbar/row; removing it would shift layout or make the row look broken. Pass a function child instead of an element:
```tsx
<Can I="delete" a="members">
  {({ isAllowed }) => (
    <Button disabled={!isAllowed} title={isAllowed ? undefined : "Missing permission: members.delete"}>
      Delete
    </Button>
  )}
</Can>
```

**Modals**: gate the *trigger*, the same as any button — if the user can't open a create/edit modal, `<Can>` around the trigger button is enough. If the modal can also be reached another way (a keyboard shortcut, a deep link), gate the modal's own mount too, not just the button that usually opens it.

**Selects**: filter the *options*, not just the field. A role-assignment `<Select>` must never list a role the current user isn't permitted to grant — showing every role and only validating on submit lets someone assign a role in the UI, get a 403, and now knows a role name they otherwise wouldn't have discovered. Build the option list from the intersection of "roles that exist" and "roles this user's own permissions allow granting."

## Page-level guards

```tsx
// entities/permission/ui/require-permission.tsx
"use client";

import type { ReactNode } from "react";
import { useCan } from "@/entities/permission";

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
```

This is still UX — for a real boundary, check on the server too, in the same page's Server Component, before any prefetch runs:
```tsx
// app/[orgId]/billing/page.tsx
import { verifySession } from "@/shared/lib/session";
import { redirect } from "next/navigation";

export default async function BillingPage({ params }: { params: { orgId: string } }) {
  const session = await verifySession();
  if (!session.permissions.includes("billing.read")) {
    redirect("/403");
  }
  // ...prefetch + render, same pattern as every other page
}
```
The client-side `RequirePermission` then just avoids a flash of content before the redirect resolves, or handles the case where a permission is revoked mid-session and a cached client render briefly shows stale UI.

## Switching organizations

Changing the active organization changes what the user can see and do entirely — clear query cache scoped to the old organization when it happens, the same way `references/data-layer.md` already treats mutations as invalidation triggers:
```tsx
async function switchOrganization(newOrganizationId: string) {
  await queryClient.cancelQueries();
  queryClient.clear(); // every cached query belonged to the old organization's scope
  // ...update the session/cookie server-side, then reload permissions for newOrganizationId
}
```
A stale query cache surviving an org switch is how one organization's data briefly renders inside another's view.

## Where this lives

`entities/permission/` — a business concept shared by every module that renders a gated button, page, or modal, per the same rule as any other cross-module concept (see `references/layers-and-modules.md`). `PermissionProvider` gets wired into `core/providers.tsx` (or wherever `QueryClientProvider`/`MotionProvider` already live) alongside them, not reinvented per module.
