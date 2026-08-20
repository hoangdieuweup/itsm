import { createNavigation } from "next-intl/navigation";
import { routing } from "./routing";

/**
 * Locale-aware navigation primitives. Use these instead of `next/link`,
 * `next/navigation`'s `redirect` / `useRouter` / `usePathname` so every
 * URL automatically carries the active locale prefix.
 */
export const { Link, redirect, usePathname, useRouter } =
  createNavigation(routing);
