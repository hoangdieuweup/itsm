"use client";

import { useMutation } from "@tanstack/react-query";
import { runLogQuery, type LogQueryValues } from "../api/fetchers";

/**
 * Running a query is an action, not a cacheable resource — every "Run
 * query" click is a fresh POST, so this is a mutation, not a useQuery.
 */
export function useRunLogQuery(environmentId: string) {
  return useMutation({
    mutationFn: (data: LogQueryValues) => runLogQuery(environmentId, data),
  });
}
