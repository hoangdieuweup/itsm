"use client";

import { useSuspenseQuery } from "@tanstack/react-query";
import { fetchAuthSession } from "../api/session";
import { authKeys } from "@/entities/auth";
import type { AuthSession } from "../model/session";

export function useAuthSession() {
  return useSuspenseQuery<AuthSession>({
    queryKey: authKeys.session(),
    queryFn: fetchAuthSession,
    staleTime: 30_000,
  });
}
