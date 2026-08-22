import { setRequestLocale } from "next-intl/server";
import { HydrationBoundary, dehydrate } from "@tanstack/react-query";
import { createQueryClient } from "@/shared/lib/query-client";
import { RequirePermission, NoPermission, hasPermission } from "@/entities/permission";
import { fetchAuthSession } from "@/modules/auth";
import { RESOURCES, ACTIONS } from "@/shared/constants/permissions";
import { fetchCloudflareAccount, cloudflareAccountsKeys } from "@/entities/cloudflare-account";
import { CloudflareAccountDetailView } from "@/modules/cloudflare-accounts";

export default async function AdminCloudflareAccountDetailPage({
  params,
}: {
  params: Promise<{ locale: string; accountId: string }>;
}) {
  const { locale, accountId } = await params;
  setRequestLocale(locale);

  const session = await fetchAuthSession();
  const canView = hasPermission(session, RESOURCES.CLOUDFLARE_ACCOUNT, ACTIONS.VIEW);

  const queryClient = createQueryClient();
  if (canView) {
    await queryClient.prefetchQuery({
      queryKey: cloudflareAccountsKeys.detail(accountId),
      queryFn: () => fetchCloudflareAccount(accountId),
    });
  }

  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <RequirePermission
        resource={RESOURCES.CLOUDFLARE_ACCOUNT}
        action={ACTIONS.VIEW}
        fallback={<NoPermission />}
      >
        <CloudflareAccountDetailView accountId={accountId} />
      </RequirePermission>
    </HydrationBoundary>
  );
}
