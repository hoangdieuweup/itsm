"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Drawer } from "@/shared/ui/drawer";
import { ProjectDetailView } from "@/modules/projects";
import { TunnelsManager } from "@/modules/cloudflare-tunnels";
import { LogViewerManager } from "@/modules/log-viewer";
import { AlertingManager } from "@/modules/alerting";
import type { Environment } from "@/entities/environment";
import { IconCloud } from "@/shared/ui/icons";

export function ProjectDetailClient({ projectId }: { projectId: string }) {
  const t = useTranslations("projects");
  const tTunnels = useTranslations("cloudflareTunnels");
  const tLogs = useTranslations("logViewer");
  const tAlerting = useTranslations("alerting");
  const [tunnelsDrawerTarget, setTunnelsDrawerTarget] = useState<Environment | null>(null);
  const [logsDrawerTarget, setLogsDrawerTarget] = useState<Environment | null>(null);
  const [alertingDrawerTarget, setAlertingDrawerTarget] = useState<Environment | null>(null);

  return (
    <>
      <ProjectDetailView
        projectId={projectId}
        onManageTunnels={setTunnelsDrawerTarget}
        onManageLogs={setLogsDrawerTarget}
        onManageAlerting={setAlertingDrawerTarget}
      />
      {tunnelsDrawerTarget && (
        <Drawer
          icon={IconCloud}
          title={tunnelsDrawerTarget.name}
          subtitle={tTunnels("drawerSubtitle")}
          onClose={() => setTunnelsDrawerTarget(null)}
          closeLabel={t("actions.closeTunnelsDrawer")}
        >
          <TunnelsManager environmentId={tunnelsDrawerTarget.id} />
        </Drawer>
      )}
      {logsDrawerTarget && (
        <Drawer
          icon={IconCloud}
          title={logsDrawerTarget.name}
          subtitle={tLogs("drawerSubtitle")}
          onClose={() => setLogsDrawerTarget(null)}
          closeLabel={t("actions.closeLogsDrawer")}
        >
          <LogViewerManager environmentId={logsDrawerTarget.id} />
        </Drawer>
      )}
      {alertingDrawerTarget && (
        <Drawer
          icon={IconCloud}
          title={alertingDrawerTarget.name}
          subtitle={tAlerting("drawerSubtitle")}
          onClose={() => setAlertingDrawerTarget(null)}
          closeLabel={t("actions.closeAlertingDrawer")}
        >
          <AlertingManager environmentId={alertingDrawerTarget.id} />
        </Drawer>
      )}
    </>
  );
}
