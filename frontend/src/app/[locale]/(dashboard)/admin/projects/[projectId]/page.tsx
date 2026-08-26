import { setRequestLocale } from "next-intl/server";
import { HydrationBoundary, dehydrate } from "@tanstack/react-query";
import { createQueryClient } from "@/shared/lib/query-client";
import { RequirePermission, NoPermission, hasPermission } from "@/entities/permission";
import { fetchAuthSession } from "@/modules/auth";
import { RESOURCES, ACTIONS } from "@/shared/constants/permissions";
import { fetchProject, projectsKeys } from "@/entities/project";
import { fetchProjectEnvironments, environmentsKeys } from "@/entities/environment";
import { fetchNotificationChannels, notificationChannelsKeys } from "@/entities/notification-channel";
import { NotificationChannelsSection } from "@/modules/notifications";
import { ProjectDetailClient } from "./project-detail-client";

export default async function AdminProjectDetailPage({
  params,
}: {
  params: Promise<{ locale: string; projectId: string }>;
}) {
  const { locale, projectId } = await params;
  setRequestLocale(locale);

  const session = await fetchAuthSession();
  const canReadProjects = hasPermission(session, RESOURCES.PROJECT, ACTIONS.READ);
  const canReadNotificationChannels = hasPermission(
    session,
    RESOURCES.NOTIFICATION_CHANNEL,
    ACTIONS.READ,
  );

  const queryClient = createQueryClient();
  const prefetches = [];
  if (canReadProjects) {
    prefetches.push(
      queryClient.prefetchQuery({
        queryKey: projectsKeys.detail(projectId),
        queryFn: () => fetchProject(projectId),
      }),
      queryClient.prefetchQuery({
        queryKey: environmentsKeys.forProject(projectId),
        queryFn: () => fetchProjectEnvironments(projectId),
      }),
    );
  }
  if (canReadNotificationChannels) {
    prefetches.push(
      queryClient.prefetchQuery({
        queryKey: notificationChannelsKeys.list(projectId),
        queryFn: () => fetchNotificationChannels(projectId),
      }),
    );
  }
  await Promise.all(prefetches);

  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <RequirePermission
        resource={RESOURCES.PROJECT}
        action={ACTIONS.READ}
        fallback={<NoPermission />}
      >
        <ProjectDetailClient projectId={projectId}>
          <RequirePermission
            resource={RESOURCES.NOTIFICATION_CHANNEL}
            action={ACTIONS.READ}
            fallback={null}
          >
            <NotificationChannelsSection projectId={projectId} />
          </RequirePermission>
        </ProjectDetailClient>
      </RequirePermission>
    </HydrationBoundary>
  );
}
