import { setRequestLocale } from "next-intl/server";
import { HydrationBoundary, dehydrate } from "@tanstack/react-query";
import { createQueryClient } from "@/shared/lib/query-client";
import { RequirePermission, NoPermission } from "@/entities/permission";
import {
  UsersPageContent,
  fetchUsers,
  usersKeys,
} from "@/modules/users";

export default async function AdminUsersPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);

  const queryClient = createQueryClient();
  await queryClient.prefetchQuery({
    queryKey: usersKeys.list({ limit: 50, offset: 0 }),
    queryFn: () => fetchUsers(50, 0),
  });

  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <RequirePermission
        resource="user"
        action="read"
        fallback={<NoPermission />}
      >
        <UsersPageContent />
      </RequirePermission>
    </HydrationBoundary>
  );
}
