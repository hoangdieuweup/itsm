import { setRequestLocale } from "next-intl/server";
import { HydrationBoundary, dehydrate } from "@tanstack/react-query";
import { createQueryClient } from "@/shared/lib/query-client";
import {
  RequirePermission,
  NoPermission,
  hasPermission,
  fetchProjectPermissions,
  projectPermissionsKeys,
} from "@/entities/permission";
import { fetchAuthSession } from "@/modules/auth";
import { RESOURCES, ACTIONS } from "@/shared/constants/permissions";
import { fetchEnvironmentById, environmentsKeys, type Environment } from "@/entities/environment";
import { AlertingPageContent } from "@/modules/alerting";

export default async function AdminEnvironmentAlertingPage({
  params,
}: {
  params: Promise<{ locale: string; environmentId: string }>;
}) {
  const { locale, environmentId } = await params;
  setRequestLocale(locale);

  const session = await fetchAuthSession();
  const canRead = hasPermission(session, RESOURCES.ENVIRONMENT, ACTIONS.READ);

  const queryClient = createQueryClient();
  if (canRead) {
    await queryClient.prefetchQuery({
      queryKey: environmentsKeys.detail(environmentId),
      queryFn: () => fetchEnvironmentById(environmentId),
    });
    const environment = queryClient.getQueryData<Environment>(environmentsKeys.detail(environmentId));
    if (environment) {
      await queryClient.prefetchQuery({
        queryKey: projectPermissionsKeys.forProject(environment.projectId),
        queryFn: () => fetchProjectPermissions(environment.projectId),
      });
    }
  }

  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <RequirePermission resource={RESOURCES.ENVIRONMENT} action={ACTIONS.READ} fallback={<NoPermission />}>
        <AlertingPageContent environmentId={environmentId} />
      </RequirePermission>
    </HydrationBoundary>
  );
}
