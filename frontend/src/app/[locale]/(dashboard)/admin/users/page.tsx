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

  const session = await fetchAuthSession();
  const canReadUsers = hasPermission(session, RESOURCES.USER, ACTIONS.READ);

  const queryClient = createQueryClient();
  if (canReadUsers) {
    await queryClient.prefetchQuery({
      queryKey: usersKeys.list({ limit: 50, offset: 0 }),
      queryFn: () => fetchUsers(50, 0),
    });
  }

  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <RequirePermission
        resource={RESOURCES.USER}
        action={ACTIONS.READ}
        fallback={<NoPermission />}
      >
        <UsersPageContent />
      </RequirePermission>
    </HydrationBoundary>
  );
}

