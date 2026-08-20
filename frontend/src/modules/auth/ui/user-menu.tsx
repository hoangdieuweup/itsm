"use client";

import { Avatar, AvatarFallback } from "@/shared/ui/avatar";
import { useAuthSession } from "../hooks/use-auth-session";

/**
 * Renders a signed-out fallback today; the authenticated dropdown
 * (profile/logout) is added once sub-issue #5 makes `useAuthSession`
 * resolve real DX-backed sessions. Only ever rendered inside `AuthGuard`
 * (see `(dashboard)/layout.tsx`), so the session query is already
 * prefetched/hydrated and this read never suspends on its own.
 */
export function UserMenu() {
  const { data: session } = useAuthSession();

  if (session.status !== "authenticated" || !session.user) {
    return null;
  }

  const initials = session.user.name
    .split(" ")
    .map((part) => part[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();

  return (
    <Avatar>
      <AvatarFallback>{initials}</AvatarFallback>
    </Avatar>
  );
}
