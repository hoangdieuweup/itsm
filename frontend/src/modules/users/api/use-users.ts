"use client";

import { useSuspenseQuery } from "@tanstack/react-query";
import { fetchUsers } from "./fetchers";
import { usersKeys } from "./query-keys";
import type { UsersPage } from "../model/schema";

/**
 * Suspense query for reading users list.
 * Expects parent Server Component to prefetch `usersKeys.list({ limit, offset })`.
 */
export function useUsers(limit = 50, offset = 0) {
  return useSuspenseQuery<UsersPage>({
    queryKey: usersKeys.list({ limit, offset }),
    queryFn: () => fetchUsers(limit, offset),
    staleTime: 30_000,
  });
}
