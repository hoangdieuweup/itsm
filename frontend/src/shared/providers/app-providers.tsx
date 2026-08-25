"use client";

import { useState } from "react";
import {
  QueryClientProvider,
  QueryErrorResetBoundary,
} from "@tanstack/react-query";
import { createQueryClient } from "@/shared/lib/query-client";
import { MotionProvider } from "@/shared/lib/motion";
import { Toaster } from "@/shared/ui/sonner";

/**
 * Framework-wiring providers shared by every route: the TanStack Query
 * client, the reset boundary each route's error.tsx relies on, the
 * lazy-loaded Framer Motion feature set, and the global toast container.
 * Mounted once in app/layout.tsx.
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
        {() => (
          <MotionProvider>
            {children}
            <Toaster />
          </MotionProvider>
        )}
      </QueryErrorResetBoundary>
    </QueryClientProvider>
  );
}

