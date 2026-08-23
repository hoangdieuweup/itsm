"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Globe, Plus, Pencil, Trash2 } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { ConfirmDialog } from "@/shared/ui/confirm-dialog";
import { Can } from "@/entities/permission";
import { ACTIONS, PERMISSIONS } from "@/shared/constants/permissions";
import { useTunnelHostnamesQuery, useRemoveTunnelHostname } from "../hooks/use-tunnel-hostnames";
import type { TunnelPublicHostname } from "../model/schema";
import { HostnameFormDialog } from "./hostname-form-dialog";

export function TunnelHostnamesPanel({ environmentId, tunnelId }: { environmentId: string; tunnelId: string }) {
  const t = useTranslations("cloudflareTunnels");
  const { data: hostnames = [] } = useTunnelHostnamesQuery(environmentId, tunnelId, true);
  const removeHostname = useRemoveTunnelHostname(environmentId, tunnelId);

  const [formTarget, setFormTarget] = useState<TunnelPublicHostname | "create" | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<TunnelPublicHostname | null>(null);

  return (
    <section className="flex flex-col gap-3 rounded-xl border bg-card p-5">
      <div className="flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-sm font-bold text-foreground">
          <Globe className="size-4" aria-hidden="true" /> {t("hostnames.title")}
        </h2>
        <Can I={ACTIONS.MANAGE} a={PERMISSIONS.CLOUDFLARE_ACCOUNT.RESOURCE}>
          <Button size="sm" onClick={() => setFormTarget("create")}>
            <Plus className="mr-1.5 size-3.5" aria-hidden="true" /> {t("hostnames.add")}
          </Button>
        </Can>
      </div>

      {hostnames.length === 0 ? (
        <p className="text-sm text-muted-foreground">{t("hostnames.empty")}</p>
      ) : (
        <div className="flex flex-col divide-y">
          {hostnames.map((hostname) => (
            <div key={hostname.id} className="flex items-center justify-between py-2 text-sm">
              <div className="flex flex-col">
                <span className="font-medium text-foreground">{hostname.hostname}</span>
                <span className="text-xs text-muted-foreground">{hostname.service}</span>
              </div>
              <Can I={ACTIONS.MANAGE} a={PERMISSIONS.CLOUDFLARE_ACCOUNT.RESOURCE}>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => setFormTarget(hostname)}
                    aria-label={t("hostnames.edit")}
                    className="cursor-pointer text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                  >
                    <Pencil className="size-3.5" aria-hidden="true" />
                  </button>
                  <button
                    type="button"
                    onClick={() => setDeleteTarget(hostname)}
                    aria-label={t("hostnames.remove")}
                    className="cursor-pointer text-muted-foreground hover:text-destructive focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                  >
                    <Trash2 className="size-3.5" aria-hidden="true" />
                  </button>
                </div>
              </Can>
            </div>
          ))}
        </div>
      )}

      {formTarget !== null && (
        <HostnameFormDialog
          environmentId={environmentId}
          tunnelId={tunnelId}
          hostname={formTarget === "create" ? null : formTarget}
          onClose={() => setFormTarget(null)}
        />
      )}

      <ConfirmDialog
        isOpen={deleteTarget !== null}
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => {
          if (deleteTarget) {
            removeHostname.mutate(deleteTarget.id, { onSuccess: () => setDeleteTarget(null) });
          }
        }}
        title={t("hostnames.deleteConfirm.title")}
        description={t("hostnames.deleteConfirm.description", { hostname: deleteTarget?.hostname ?? "" })}
        variant="destructive"
        isLoading={removeHostname.isPending}
      />
    </section>
  );
}
