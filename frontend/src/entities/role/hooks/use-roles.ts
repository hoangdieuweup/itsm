"use client";

import { useSuspenseQuery, useQuery } from "@tanstack/react-query";
import { fetchRoles, fetchPermissions } from "../api/fetchers";
import { rolesKeys } from "../api/query-keys";
import type { RolesPage, PermissionsList } from "../model/schema";

/**
 * Suspense query for reading roles list.
 */
export function useRoles(limit = 50, offset = 0) {
  return useSuspenseQuery<RolesPage>({
    queryKey: rolesKeys.list({ limit, offset }),
    queryFn: () => fetchRoles(limit, offset),
    staleTime: 30_000,
  });
}

/**
 * Standard query for reading roles list with enabled control (e.g. inside modal dialogs).
 */
export function useRolesQuery(limit = 100, offset = 0, enabled = true) {
  return useQuery<RolesPage>({
    queryKey: rolesKeys.list({ limit, offset }),
    queryFn: () => fetchRoles(limit, offset),
    staleTime: 30_000,
    enabled,
  });
}

/**
 * Query for reading fixed permissions catalog.
 */
export function usePermissions() {
  return useQuery<PermissionsList>({
    queryKey: rolesKeys.permissions(),
    queryFn: fetchPermissions,
    staleTime: Infinity,
  });
}
