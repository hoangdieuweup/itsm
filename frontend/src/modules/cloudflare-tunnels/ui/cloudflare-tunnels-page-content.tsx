"use client";

import { useTranslations } from "next-intl";
import { useEnvironmentQuery } from "@/entities/environment";
import { TunnelsManager } from "./tunnels-manager";

export function CloudflareTunnelsPageContent({ environmentId }: { environmentId: string }) {
  const t = useTranslations("cloudflareTunnels");
  const { data: environment } = useEnvironmentQuery(environmentId);

  return (
    <div className="flex flex-1 flex-col gap-6 p-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-xl font-bold text-foreground">{environment.name}</h1>
        <p className="text-sm text-muted-foreground">{t(`environmentTypes.${environment.type}`)}</p>
      </div>

      <TunnelsManager environmentId={environmentId} />
    </div>
  );
}
