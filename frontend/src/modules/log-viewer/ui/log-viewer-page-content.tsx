"use client";

import { useEnvironmentQuery } from "@/entities/environment";
import { CanInProject, NoPermission, ProjectPermissionProvider } from "@/entities/permission";
import { ACTIONS, RESOURCES } from "@/shared/constants/permissions";
import { LogViewerManager } from "./log-viewer-manager";

export function LogViewerPageContent({ environmentId }: { environmentId: string }) {
  const { data: environment } = useEnvironmentQuery(environmentId);

  return (
    <ProjectPermissionProvider projectId={environment.projectId}>
      <CanInProject I={ACTIONS.READ} a={RESOURCES.PROJECT_LOKI_CONFIG} fallback={<NoPermission />}>
        <div className="flex flex-1 flex-col gap-6 p-6">
          <LogViewerManager environmentId={environmentId} />
        </div>
      </CanInProject>
    </ProjectPermissionProvider>
  );
}
