import { setRequestLocale } from "next-intl/server";
import { HydrationBoundary, dehydrate } from "@tanstack/react-query";
import { createQueryClient } from "@/shared/lib/query-client";
import {
  RequirePermission,
  NoPermission,
  hasPermission,
} from "@/entities/permission";
import { fetchAuthSession } from "@/modules/auth";
import { RESOURCES, ACTIONS } from "@/shared/constants/permissions";
import {
  fetchRoles,
  fetchPermissions,
  rolesKeys,
} from "@/entities/role";
import { RolesPageContent } from "@/modules/roles";

export default async function AdminRolesPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);

  const session = await fetchAuthSession();
  const canReadRoles = hasPermission(session, RESOURCES.ROLE, ACTIONS.READ);

  const queryClient = createQueryClient();
  if (canReadRoles) {
    await Promise.all([
      queryClient.prefetchQuery({
        queryKey: rolesKeys.list({ limit: 50, offset: 0 }),
        queryFn: () => fetchRoles(50, 0),
      }),
      queryClient.prefetchQuery({
        queryKey: rolesKeys.permissions(),
        queryFn: fetchPermissions,
      }),
    ]);
  }

  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <RequirePermission
        resource={RESOURCES.ROLE}
        action={ACTIONS.READ}
        fallback={<NoPermission />}
      >
        <RolesPageContent />
      </RequirePermission>
    </HydrationBoundary>
  );
}

