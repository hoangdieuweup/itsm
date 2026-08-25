"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { ScrollText, Siren, Waypoints } from "lucide-react";
import { Drawer } from "@/shared/ui/drawer";
import { ProjectDetailView } from "@/modules/projects";
import { TunnelsManager } from "@/modules/cloudflare-tunnels";
import { LogViewerManager } from "@/modules/log-viewer";
import { AlertingManager } from "@/modules/alerting";
import type { Environment } from "@/entities/environment";


export function ProjectDetailClient({ projectId }: { projectId: string }) {
  const t = useTranslations("projects");
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
          icon={Waypoints}
          title={tunnelsDrawerTarget.name}
          onClose={() => setTunnelsDrawerTarget(null)}
          closeLabel={t("actions.closeTunnelsDrawer")}
        >
          <TunnelsManager environmentId={tunnelsDrawerTarget.id} />
        </Drawer>
      )}
      {logsDrawerTarget && (
        <Drawer
          icon={ScrollText}
          title={logsDrawerTarget.name}
          onClose={() => setLogsDrawerTarget(null)}
          closeLabel={t("actions.closeLogsDrawer")}
        >
          <LogViewerManager environmentId={logsDrawerTarget.id} />
        </Drawer>
      )}
      {alertingDrawerTarget && (
        <Drawer
          icon={Siren}
          title={alertingDrawerTarget.name}
          onClose={() => setAlertingDrawerTarget(null)}
          closeLabel={t("actions.closeAlertingDrawer")}
        >
          <AlertingManager environmentId={alertingDrawerTarget.id} />
        </Drawer>
      )}
    </>
  );
}
