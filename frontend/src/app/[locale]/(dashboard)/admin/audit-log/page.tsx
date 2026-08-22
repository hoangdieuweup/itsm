import { setRequestLocale } from "next-intl/server";
import { HydrationBoundary, dehydrate } from "@tanstack/react-query";
import { createQueryClient } from "@/shared/lib/query-client";
import { RequirePermission, NoPermission, hasPermission } from "@/entities/permission";
import { fetchAuthSession } from "@/modules/auth";
import { RESOURCES, ACTIONS } from "@/shared/constants/permissions";
import { fetchAuditLogs, auditLogsKeys, AuditLogPageContent } from "@/modules/audit-log";

export default async function AdminAuditLogPage({
  params,
}: {
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  setRequestLocale(locale);

  const session = await fetchAuthSession();
  const canRead = hasPermission(session, RESOURCES.AUDIT_LOG, ACTIONS.READ);

  const queryClient = createQueryClient();
  if (canRead) {
    await queryClient.prefetchQuery({
      queryKey: auditLogsKeys.list({ limit: 50, offset: 0 }),
      queryFn: () => fetchAuditLogs({ limit: 50, offset: 0 }),
    });
  }

  return (
    <HydrationBoundary state={dehydrate(queryClient)}>
      <RequirePermission
        resource={RESOURCES.AUDIT_LOG}
        action={ACTIONS.READ}
        fallback={<NoPermission />}
      >
        <AuditLogPageContent />
      </RequirePermission>
    </HydrationBoundary>
  );
}
