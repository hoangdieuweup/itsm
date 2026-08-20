import { QueryClient } from "@tanstack/react-query";

/**
 * One factory shared by the server (per-request prefetch) and the client
 * (`core/providers.tsx`) so query defaults never drift between the two.
 */
export function createQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000,
      },
    },
  });
}
