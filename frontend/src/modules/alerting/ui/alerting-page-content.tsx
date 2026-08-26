"use client";

import { useTranslations } from "next-intl";
import { useEnvironmentQuery } from "@/entities/environment";
import { ProjectPermissionProvider } from "@/entities/permission";
import { AlertingManager } from "./alerting-manager";

export function AlertingPageContent({ environmentId }: { environmentId: string }) {
  const t = useTranslations("alerting");
  const { data: environment } = useEnvironmentQuery(environmentId);

  return (
    <div className="flex flex-1 flex-col gap-6 p-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-xl font-bold text-foreground">{environment.name}</h1>
        <p className="text-sm text-muted-foreground">{t("subtitle")}</p>
      </div>

      <ProjectPermissionProvider projectId={environment.projectId}>
        <AlertingManager environmentId={environmentId} />
      </ProjectPermissionProvider>
    </div>
  );
}
