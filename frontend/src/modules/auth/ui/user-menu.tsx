"use client";

import { useTranslations } from "next-intl";
import { LogOut } from "lucide-react";

import { Avatar, AvatarFallback } from "@/shared/ui/avatar";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/shared/ui/dropdown-menu";
import { useAuthSession } from "../hooks/use-auth-session";
import { useLogout } from "../hooks/use-logout";

/**
 * Authenticated user avatar with a dropdown containing profile info and
 * logout action. Only rendered inside `AuthGuard` (dashboard layout), so
 * the session query is already prefetched/hydrated — this read never
 * suspends on its own.
 */
export function UserMenu() {
  const t = useTranslations("auth.userMenu");
  const { data: session } = useAuthSession();
  const logout = useLogout();

  if (session.status !== "authenticated" || !session.user) {
    return null;
  }

  const initials =
    (session.user.name || "")
      .trim()
      .split(/\s+/)
      .map((part) => part[0] || "")
      .join("")
      .slice(0, 2)
      .toUpperCase() || "U";

  return (
    <DropdownMenu>
      <DropdownMenuTrigger className="cursor-pointer rounded-full outline-none ring-offset-background focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2">
        <Avatar>
          <AvatarFallback>{initials}</AvatarFallback>
        </Avatar>
      </DropdownMenuTrigger>

      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuLabel className="font-normal">
          <div className="flex flex-col gap-1">
            <p className="text-sm font-medium leading-none">{session.user.name}</p>
            <p className="text-xs leading-none text-muted-foreground">{session.user.email}</p>
            {session.roleName && (
              <p className="text-xs leading-none text-muted-foreground/70 capitalize">
                {session.roleName}
              </p>
            )}
          </div>
        </DropdownMenuLabel>

        <DropdownMenuSeparator />

        <DropdownMenuItem
          onClick={() => logout.mutate()}
          disabled={logout.isPending}
          className="cursor-pointer text-destructive focus:text-destructive"
        >
          <LogOut className="mr-2 size-4" aria-hidden />
          {t("logout")}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
