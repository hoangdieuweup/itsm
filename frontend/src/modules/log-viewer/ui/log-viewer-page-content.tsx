"use client";

import { useEnvironmentQuery } from "@/entities/environment";
import { ProjectPermissionProvider } from "@/entities/permission";
import { LogViewerManager } from "./log-viewer-manager";

export function LogViewerPageContent({ environmentId }: { environmentId: string }) {
  const { data: environment } = useEnvironmentQuery(environmentId);

  return (
    <div className="flex flex-1 flex-col gap-6 p-6">
      <ProjectPermissionProvider projectId={environment.projectId}>
        <LogViewerManager environmentId={environmentId} />
      </ProjectPermissionProvider>
    </div>
  );
}
