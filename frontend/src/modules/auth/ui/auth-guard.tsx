"use client";

import { useEffect } from "react";
import { useRouter } from "@/shared/lib/i18n/navigation";
import { ROUTES } from "@/shared/constants/routes";
import { PermissionProvider, type Permission } from "@/entities/permission";
import { useAuthSession } from "../hooks/use-auth-session";
import { isAuthenticated } from "../model/session";

export function AuthGuard({ children }: { children: React.ReactNode }) {
  const { data: session } = useAuthSession();
  const router = useRouter();

  const isAuth = isAuthenticated(session);

  useEffect(() => {
    if (!isAuth) {
      router.replace(ROUTES.login);
    }
  }, [isAuth, router]);

  if (!isAuth) {
    return null;
  }


  return (
    <PermissionProvider permissions={session.permissions as Permission[]}>
      {children}
    </PermissionProvider>
  );
}
