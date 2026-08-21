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

## Typed Constants & Pure `hasPermission` (Never Hardcode Strings)

Do not use bare strings like `"user"`, `"read"`, `"authenticated"` across components. Use centralized constants from `shared/constants/` and the pure `hasPermission` helper:

```tsx
// shared/constants/permissions.ts
export const RESOURCES = {
  ROLE: "role",
  PERMISSION: "permission",
  USER: "user",
} as const;

export const ACTIONS = {
  CREATE: "create",
  READ: "read",
  UPDATE: "update",
  DELETE: "delete",
  UPDATE_STATUS: "update_status",
  ASSIGN_ROLE: "assign_role",
} as const;
```

```tsx
// entities/permission/lib/permission.ts
import { AUTH_STATUS } from "@/shared/constants/auth";

export function hasPermission(
  source: HasPermissions | readonly string[] | string[] | null | undefined,
  resource: string,
  action: string,
): boolean {
  if (!source) return false;
  if ("status" in source) {
    if (source.status !== AUTH_STATUS.AUTHENTICATED) return false;
    return Array.isArray(source.permissions)
      ? source.permissions.includes(`${resource}.${action}`)
      : false;
  }
  if ("permissions" in source && Array.isArray(source.permissions)) {
    return source.permissions.includes(`${resource}.${action}`);
  }
  if (Array.isArray(source)) {
    return source.includes(`${resource}.${action}`);
  }
  return false;
}
```

## `<Can>` — buttons, modals, any single element

Use strongly typed constants with `<Can>`:

```tsx
<Can I={ACTIONS.CREATE} a={RESOURCES.ROLE}>
  <CreateRoleButton />
</Can>
```

**Hide** — for nav items, whole sections, anything where removing it entirely doesn't break layout:
```tsx
<Can I={ACTIONS.DELETE} a={RESOURCES.USER}>
  <DeleteButton />
</Can>
```

**Disable** — for an action button that's part of a fixed toolbar/row; removing it would shift layout or make the row look broken. Pass a function child instead of an element:
```tsx
<Can I={ACTIONS.DELETE} a={RESOURCES.USER}>
  {({ isAllowed }) => (
    <Button disabled={!isAllowed} title={isAllowed ? undefined : "Missing permission: user.delete"}>
      Delete
    </Button>
  )}
</Can>
```

**Modals**: gate the *trigger*, the same as any button — if the user can't open a create/edit modal, `<Can>` around the trigger button is enough. If the modal can also be reached another way (a keyboard shortcut, a deep link), gate the modal's own mount too, not just the button that usually opens it.

**Selects**: filter the *options*, not just the field. A role-assignment `<Select>` must never list a role the current user isn't permitted to grant — showing every role and only validating on submit lets someone assign a role in the UI, get a 403, and now knows a role name they otherwise wouldn't have discovered. Build the option list from the intersection of "roles that exist" and "roles this user's own permissions allow granting."

## Page-level guards & Server Component SSR Prefetch

```tsx
// entities/permission/ui/require-permission.tsx
"use client";

import type { ReactNode } from "react";
import { useCan } from "../model/permission-context";

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

### SSR Prefetch Guarding in Server Components (CRITICAL)

Server Component pages run on Node.js server during SSR **before** any client React context exists. `queryClient.prefetchQuery` must be guarded with `hasPermission` before executing prefetch requests:

```tsx
// app/[locale]/(dashboard)/admin/users/page.tsx
import { fetchAuthSession } from "@/modules/auth";
import { hasPermission, RequirePermission, NoPermission } from "@/entities/permission";
import { RESOURCES, ACTIONS } from "@/shared/constants/permissions";
import { UsersPageContent, fetchUsers, usersKeys } from "@/modules/users";

export default async function AdminUsersPage() {
  const session = await fetchAuthSession();
  const canReadUsers = hasPermission(session, RESOURCES.USER, ACTIONS.READ);

  const queryClient = createQueryClient();
  if (canReadUsers) {
    await queryClient.prefetchQuery({
      queryKey: usersKeys.list({ limit: 50, offset: 0 }),
      queryFn: () => fetchUsers(50, 0),
    });
  }

  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <RequirePermission
        resource={RESOURCES.USER}
        action={ACTIONS.READ}
        fallback={<NoPermission />}
      >
        <UsersPageContent />
      </RequirePermission>
    </HydrationBoundary>
  );
}
```
Client `<RequirePermission>` and `<Can>` are client UX barriers only. The server-side guard ensures unauthorized users do not initiate prefetch requests on protected backend endpoints.


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
