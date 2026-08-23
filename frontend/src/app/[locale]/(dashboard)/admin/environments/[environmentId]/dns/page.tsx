import { setRequestLocale } from "next-intl/server";
import { HydrationBoundary, dehydrate } from "@tanstack/react-query";
import { createQueryClient } from "@/shared/lib/query-client";
import { RequirePermission, NoPermission, hasPermission } from "@/entities/permission";
import { fetchAuthSession } from "@/modules/auth";
import { RESOURCES, ACTIONS } from "@/shared/constants/permissions";
import { fetchEnvironmentById, environmentsKeys } from "@/entities/environment";
import { CloudflareDnsPageContent } from "@/modules/cloudflare-dns";

export default async function AdminEnvironmentDnsPage({
  params,
}: {
  params: Promise<{ locale: string; environmentId: string }>;
}) {
  const { locale, environmentId } = await params;
  setRequestLocale(locale);

  const session = await fetchAuthSession();
  const canView = hasPermission(session, RESOURCES.CLOUDFLARE_ACCOUNT, ACTIONS.VIEW);

  const queryClient = createQueryClient();
  if (canView) {
    await queryClient.prefetchQuery({
      queryKey: environmentsKeys.detail(environmentId),
      queryFn: () => fetchEnvironmentById(environmentId),
    });
  }

  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <RequirePermission
        resource={RESOURCES.CLOUDFLARE_ACCOUNT}
        action={ACTIONS.VIEW}
        fallback={<NoPermission />}
      >
        <CloudflareDnsPageContent environmentId={environmentId} />
      </RequirePermission>
    </HydrationBoundary>
  );
}
