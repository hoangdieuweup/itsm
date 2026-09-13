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
import { fetchEnvironmentById, environmentsKeys } from "@/entities/environment";
import { LogViewerPageContent } from "@/modules/log-viewer";

export default async function ProjectEnvironmentLogsPage({
  params,
}: {
  params: Promise<{ locale: string; projectId: string; environmentId: string }>;
}) {
  const { locale, projectId, environmentId } = await params;
  setRequestLocale(locale);

  const session = await fetchAuthSession();
  const canView = hasPermission(session, RESOURCES.ENVIRONMENT, ACTIONS.READ);

  const queryClient = createQueryClient();
  if (canView) {
    await Promise.all([
      queryClient.prefetchQuery({
        queryKey: environmentsKeys.detail(environmentId),
        queryFn: () => fetchEnvironmentById(environmentId),
      }),
      queryClient.prefetchQuery({
        queryKey: projectPermissionsKeys.forProject(projectId),
        queryFn: () => fetchProjectPermissions(projectId),
      }),
    ]);
  }

  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <RequirePermission resource={RESOURCES.ENVIRONMENT} action={ACTIONS.READ} fallback={<NoPermission />}>
        <LogViewerPageContent environmentId={environmentId} />
      </RequirePermission>
    </HydrationBoundary>
  );
}
