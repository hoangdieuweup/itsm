"use client";

import { LazyMotion, domAnimation, m } from "framer-motion";

/**
 * Loads the animation engine once via LazyMotion instead of every page that
 * imports `motion` directly pulling in the full framer-motion bundle.
 * Consumers use `m.*` from this module, never `motion` from "framer-motion".
 */
export function MotionProvider({ children }: { children: React.ReactNode }) {
  return <LazyMotion features={domAnimation}>{children}</LazyMotion>;
}

export { m };
