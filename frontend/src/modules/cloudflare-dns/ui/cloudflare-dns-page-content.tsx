"use client";

import { useTranslations } from "next-intl";
import { useEnvironmentQuery } from "@/entities/environment";
import { CanInProjectOrAccount, NoPermission, ProjectPermissionProvider } from "@/entities/permission";
import { ACTIONS, RESOURCES } from "@/shared/constants/permissions";
import { DnsManager } from "./dns-manager";

export function CloudflareDnsPageContent({ environmentId }: { environmentId: string }) {
  const t = useTranslations("cloudflareDns");
  const { data: environment } = useEnvironmentQuery(environmentId);

  return (
    <ProjectPermissionProvider projectId={environment.projectId}>
      <CanInProjectOrAccount I={ACTIONS.READ} a={RESOURCES.PROJECT_CLOUDFLARE_DNS} fallback={<NoPermission />}>
        <div className="flex flex-1 flex-col gap-6 p-6">
          <div className="flex flex-col gap-1">
            <h1 className="text-xl font-bold text-foreground">{environment.name}</h1>
            <p className="text-sm text-muted-foreground">{t(`environmentTypes.${environment.type}`)}</p>
          </div>

          <DnsManager environmentId={environmentId} />
        </div>
      </CanInProjectOrAccount>
    </ProjectPermissionProvider>
  );
}
