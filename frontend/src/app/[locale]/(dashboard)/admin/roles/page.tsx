import { setRequestLocale } from "next-intl/server";
import { HydrationBoundary, dehydrate } from "@tanstack/react-query";
import { createQueryClient } from "@/shared/lib/query-client";
import { RequirePermission, NoPermission } from "@/entities/permission";
import {
  RolesPageContent,
  fetchRoles,
  fetchPermissions,
  rolesKeys,
} from "@/modules/roles";

export default async function AdminRolesPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);

  const queryClient = createQueryClient();
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

  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <RequirePermission
        resource="role"
        action="read"
        fallback={<NoPermission />}
      >
        <RolesPageContent />
      </RequirePermission>
    </HydrationBoundary>
  );
}
