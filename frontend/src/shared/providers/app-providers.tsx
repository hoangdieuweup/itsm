"use client";

import { useState } from "react";
import {
  QueryClientProvider,
  QueryErrorResetBoundary,
} from "@tanstack/react-query";
import { createQueryClient } from "@/shared/lib/query-client";
import { MotionProvider } from "@/shared/lib/motion";

/**
 * Framework-wiring providers shared by every route: the TanStack Query
 * client, the reset boundary each route's error.tsx relies on, and the
 * lazy-loaded Framer Motion feature set. Mounted once in app/layout.tsx.
 *
 * `QueryErrorResetBoundary` has to sit above every route's error.tsx so
 * "Try again" can clear a query's cached error before Next re-renders the
 * segment (see .claude/skills/nextjs-modular-architecture/references/layer-examples.md).
 */
export function AppProviders({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(() => createQueryClient());

  return (
    <QueryClientProvider client={queryClient}>
      <QueryErrorResetBoundary>
        {() => <MotionProvider>{children}</MotionProvider>}
      </QueryErrorResetBoundary>
    </QueryClientProvider>
  );
}
