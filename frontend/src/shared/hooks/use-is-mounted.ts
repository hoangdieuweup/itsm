"use client";

import { useSyncExternalStore } from "react";

const emptySubscribe = () => () => {};

/**
 * `false` during SSR and the hydration pass, `true` afterwards.
 *
 * Use it to gate `createPortal` — rendering a portal before hydration finishes
 * produces a server/client markup mismatch.
 */
export const useIsMounted = () =>
  useSyncExternalStore(
    emptySubscribe,
    () => true,
    () => false,
  );
