import { setRequestLocale } from "next-intl/server";
import { HydrationBoundary, dehydrate } from "@tanstack/react-query";
import { createQueryClient } from "@/shared/lib/query-client";
import { RequirePermission, NoPermission, hasPermission } from "@/entities/permission";
import { fetchAuthSession } from "@/modules/auth";
import { RESOURCES, ACTIONS } from "@/shared/constants/permissions";
import { fetchProject, projectsKeys } from "@/entities/project";
import { fetchProjectEnvironments, environmentsKeys } from "@/entities/environment";
import { ProjectDetailView } from "@/modules/projects";

export default async function AdminProjectDetailPage({
  params,
}: {
  params: Promise<{ locale: string; projectId: string }>;
}) {
  const { locale, projectId } = await params;
  setRequestLocale(locale);

  const session = await fetchAuthSession();
  const canReadProjects = hasPermission(session, RESOURCES.PROJECT, ACTIONS.READ);

  const queryClient = createQueryClient();
  if (canReadProjects) {
    await Promise.all([
      queryClient.prefetchQuery({
        queryKey: projectsKeys.detail(projectId),
        queryFn: () => fetchProject(projectId),
      }),
      queryClient.prefetchQuery({
        queryKey: environmentsKeys.forProject(projectId),
        queryFn: () => fetchProjectEnvironments(projectId),
      }),
    ]);
  }

  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <RequirePermission
        resource={RESOURCES.PROJECT}
        action={ACTIONS.READ}
        fallback={<NoPermission />}
      >
        <ProjectDetailView projectId={projectId} />
      </RequirePermission>
    </HydrationBoundary>
  );
}
