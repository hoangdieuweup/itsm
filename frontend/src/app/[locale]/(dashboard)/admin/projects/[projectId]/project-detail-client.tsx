"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Drawer } from "@/shared/ui/drawer";
import { ProjectDetailView } from "@/modules/projects";
import { TunnelsManager } from "@/modules/cloudflare-tunnels";
import { AlertingManager } from "@/modules/alerting";
import { LokiManager } from "@/modules/log-viewer";
import { ProjectPermissionProvider } from "@/entities/permission";
import type { Environment } from "@/entities/environment";
import { IconCloud } from "@/shared/ui/icons";

export function ProjectDetailClient({
  projectId,
  children,
}: {
  projectId: string;
  children?: React.ReactNode;
}) {
  const t = useTranslations("projects");
  const tTunnels = useTranslations("cloudflareTunnels");
  const tAlerting = useTranslations("alerting");
  const tLogViewer = useTranslations("logViewer");
  const [tunnelsDrawerTarget, setTunnelsDrawerTarget] = useState<Environment | null>(null);
  const [lokiDrawerTarget, setLokiDrawerTarget] = useState<Environment | null>(null);
  const [alertingDrawerTarget, setAlertingDrawerTarget] = useState<Environment | null>(null);

  return (
    <>
      <ProjectDetailView
        projectId={projectId}
        onManageTunnels={setTunnelsDrawerTarget}
        onManageLoki={setLokiDrawerTarget}
        onManageAlerting={setAlertingDrawerTarget}
      >
        {children}
      </ProjectDetailView>
      {tunnelsDrawerTarget && (
        <Drawer
          icon={IconCloud}
          title={tunnelsDrawerTarget.name}
          subtitle={tTunnels("drawerSubtitle")}
          onClose={() => setTunnelsDrawerTarget(null)}
          closeLabel={t("actions.closeTunnelsDrawer")}
        >
          <ProjectPermissionProvider projectId={tunnelsDrawerTarget.projectId}>
            <TunnelsManager environmentId={tunnelsDrawerTarget.id} />
          </ProjectPermissionProvider>
        </Drawer>
      )}
      {lokiDrawerTarget && (
        <Drawer
          icon={IconCloud}
          title={lokiDrawerTarget.name}
          subtitle={tLogViewer("config.title")}
          onClose={() => setLokiDrawerTarget(null)}
          closeLabel={t("actions.closeLokiDrawer")}
        >
          <ProjectPermissionProvider projectId={lokiDrawerTarget.projectId}>
            <LokiManager environmentId={lokiDrawerTarget.id} />
          </ProjectPermissionProvider>
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
          <ProjectPermissionProvider projectId={alertingDrawerTarget.projectId}>
            <AlertingManager environmentId={alertingDrawerTarget.id} />
          </ProjectPermissionProvider>
        </Drawer>
      )}
    </>
  );
}

