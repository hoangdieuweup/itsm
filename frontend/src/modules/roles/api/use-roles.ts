"use client";

import { useSuspenseQuery, useQuery } from "@tanstack/react-query";
import { fetchRoles, fetchPermissions } from "./fetchers";
import { rolesKeys } from "./query-keys";
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
 * Query for reading fixed permissions catalog.
 */
export function usePermissions() {
  return useQuery<PermissionsList>({
    queryKey: rolesKeys.permissions(),
    queryFn: fetchPermissions,
    staleTime: Infinity, // permissions catalog is static
  });
}
