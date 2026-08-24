"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Globe, ScrollText, Siren, Waypoints } from "lucide-react";
import { Drawer } from "@/shared/ui/drawer";
import { ProjectDetailView } from "@/modules/projects";
import { DnsManager } from "@/modules/cloudflare-dns";
import { TunnelsManager } from "@/modules/cloudflare-tunnels";
import { LogViewerManager } from "@/modules/log-viewer";
import { AlertingManager } from "@/modules/alerting";
import type { Environment } from "@/entities/environment";

/**
 * Client wrapper composing `modules/projects` with `modules/cloudflare-dns`,
 * `modules/cloudflare-tunnels`, `modules/log-viewer`, and `modules/alerting`
 * — modules may not import each other directly (enforced by
 * eslint-plugin-boundaries), so this cross-module wiring lives here, at the
 * `app` layer, which is allowed to depend on any module.
 */
export function ProjectDetailClient({ projectId }: { projectId: string }) {
  const t = useTranslations("projects");
  const [dnsDrawerTarget, setDnsDrawerTarget] = useState<Environment | null>(null);
  const [tunnelsDrawerTarget, setTunnelsDrawerTarget] = useState<Environment | null>(null);
  const [logsDrawerTarget, setLogsDrawerTarget] = useState<Environment | null>(null);
  const [alertingDrawerTarget, setAlertingDrawerTarget] = useState<Environment | null>(null);

  return (
    <>
      <ProjectDetailView
        projectId={projectId}
        onManageDns={setDnsDrawerTarget}
        onManageTunnels={setTunnelsDrawerTarget}
        onManageLogs={setLogsDrawerTarget}
        onManageAlerting={setAlertingDrawerTarget}
      />
      {dnsDrawerTarget && (
        <Drawer
          icon={Globe}
          title={dnsDrawerTarget.name}
          onClose={() => setDnsDrawerTarget(null)}
          closeLabel={t("actions.closeDnsDrawer")}
        >
          <DnsManager environmentId={dnsDrawerTarget.id} />
        </Drawer>
      )}
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
