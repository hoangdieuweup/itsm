import { setRequestLocale } from "next-intl/server";
import { HydrationBoundary, dehydrate } from "@tanstack/react-query";
import { createQueryClient } from "@/shared/lib/query-client";
import { RequirePermission, NoPermission, hasPermission } from "@/entities/permission";
import { fetchAuthSession } from "@/modules/auth";
import { RESOURCES, ACTIONS } from "@/shared/constants/permissions";
import { fetchCloudflareAccounts, cloudflareAccountsKeys } from "@/entities/cloudflare-account";
import { CloudflareAccountsPageContent } from "@/modules/cloudflare-accounts";

export default async function AdminCloudflareAccountsPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);

  const session = await fetchAuthSession();
  const canView = hasPermission(session, RESOURCES.CLOUDFLARE_ACCOUNT, ACTIONS.READ);

  const queryClient = createQueryClient();
  if (canView) {
    await queryClient.prefetchQuery({
      queryKey: cloudflareAccountsKeys.list(),
      queryFn: () => fetchCloudflareAccounts(),
    });
  }

  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <RequirePermission
        resource={RESOURCES.CLOUDFLARE_ACCOUNT}
        action={ACTIONS.READ}
        fallback={<NoPermission />}
      >
        <CloudflareAccountsPageContent />
      </RequirePermission>
    </HydrationBoundary>
  );
}
