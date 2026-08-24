import { setRequestLocale } from "next-intl/server";
import { HydrationBoundary, dehydrate } from "@tanstack/react-query";
import { createQueryClient } from "@/shared/lib/query-client";
import { RequirePermission, NoPermission, hasPermission } from "@/entities/permission";
import { fetchAuthSession } from "@/modules/auth";
import { RESOURCES, ACTIONS } from "@/shared/constants/permissions";
import { fetchIncidents, incidentsKeys } from "@/entities/incident";
import { IncidentsPageContent } from "@/modules/incidents";

export default async function AdminIncidentsPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);

  const session = await fetchAuthSession();
  const canRead = hasPermission(session, RESOURCES.INCIDENT, ACTIONS.READ);

  const queryClient = createQueryClient();
  if (canRead) {
    await queryClient.prefetchQuery({
      queryKey: incidentsKeys.list({}),
      queryFn: () => fetchIncidents({}),
    });
  }

  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <RequirePermission resource={RESOURCES.INCIDENT} action={ACTIONS.READ} fallback={<NoPermission />}>
        <IncidentsPageContent />
      </RequirePermission>
    </HydrationBoundary>
  );
}
