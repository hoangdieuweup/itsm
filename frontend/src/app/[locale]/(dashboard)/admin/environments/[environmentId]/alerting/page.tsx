import { setRequestLocale } from "next-intl/server";
import { HydrationBoundary, dehydrate } from "@tanstack/react-query";
import { createQueryClient } from "@/shared/lib/query-client";
import { RequirePermission, NoPermission, hasPermission } from "@/entities/permission";
import { fetchAuthSession } from "@/modules/auth";
import { RESOURCES, ACTIONS } from "@/shared/constants/permissions";
import { fetchEnvironmentById, environmentsKeys } from "@/entities/environment";
import { AlertingPageContent } from "@/modules/alerting";

export default async function AdminEnvironmentAlertingPage({
  params,
}: {
  params: Promise<{ locale: string; environmentId: string }>;
}) {
  const { locale, environmentId } = await params;
  setRequestLocale(locale);

  const session = await fetchAuthSession();
  const canRead = hasPermission(session, RESOURCES.ALERT_RULE, ACTIONS.READ);

  const queryClient = createQueryClient();
  if (canRead) {
    await queryClient.prefetchQuery({
      queryKey: environmentsKeys.detail(environmentId),
      queryFn: () => fetchEnvironmentById(environmentId),
    });
  }

  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <RequirePermission resource={RESOURCES.ALERT_RULE} action={ACTIONS.READ} fallback={<NoPermission />}>
        <AlertingPageContent environmentId={environmentId} />
      </RequirePermission>
    </HydrationBoundary>
  );
}
