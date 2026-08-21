"use client";

import { useEffect } from "react";
import { useRouter } from "@/shared/lib/i18n/navigation";
import { ROUTES } from "@/shared/constants/routes";
import { PermissionProvider, type Permission } from "@/entities/permission";
import { useAuthSession } from "../hooks/use-auth-session";

export function AuthGuard({ children }: { children: React.ReactNode }) {
  const { data: session } = useAuthSession();
  const router = useRouter();

  useEffect(() => {
    if (session.status !== "authenticated") {
      router.replace(ROUTES.login);
    }
  }, [session.status, router]);

  if (session.status !== "authenticated") {
    return null;
  }

  return (
    <PermissionProvider permissions={session.permissions as Permission[]}>
      {children}
    </PermissionProvider>
  );
}
