"use client";

import { useTranslations } from "next-intl";
import { useEnvironmentQuery } from "@/entities/environment";
import { ProjectPermissionProvider } from "@/entities/permission";
import { LogViewerManager } from "./log-viewer-manager";

export function LogViewerPageContent({ environmentId }: { environmentId: string }) {
  const t = useTranslations("logViewer");
  const { data: environment } = useEnvironmentQuery(environmentId);

  return (
    <div className="flex flex-1 flex-col gap-6 p-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-xl font-bold text-foreground">{environment.name}</h1>
        <p className="text-sm text-muted-foreground">{t(`environmentTypes.${environment.type}`)}</p>
      </div>

      <ProjectPermissionProvider projectId={environment.projectId}>
        <LogViewerManager environmentId={environmentId} />
      </ProjectPermissionProvider>
    </div>
  );
}
