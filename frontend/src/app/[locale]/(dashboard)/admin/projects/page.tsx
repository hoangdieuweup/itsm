import { setRequestLocale } from "next-intl/server";
import { HydrationBoundary, dehydrate } from "@tanstack/react-query";
import { createQueryClient } from "@/shared/lib/query-client";
import { RequirePermission, NoPermission, hasPermission } from "@/entities/permission";
import { fetchAuthSession } from "@/modules/auth";
import { RESOURCES, ACTIONS } from "@/shared/constants/permissions";
import { fetchProjects, projectsKeys } from "@/entities/project";
import { ProjectsPageContent } from "@/modules/projects";

export default async function AdminProjectsPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);

  const session = await fetchAuthSession();
  const canReadProjects = hasPermission(session, RESOURCES.PROJECT, ACTIONS.READ);

  const queryClient = createQueryClient();
  if (canReadProjects) {
    await queryClient.prefetchQuery({
      queryKey: projectsKeys.list({ limit: 50, offset: 0 }),
      queryFn: () => fetchProjects(50, 0),
    });
  }

  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <RequirePermission
        resource={RESOURCES.PROJECT}
        action={ACTIONS.READ}
        fallback={<NoPermission />}
      >
        <ProjectsPageContent />
      </RequirePermission>
    </HydrationBoundary>
  );
}
