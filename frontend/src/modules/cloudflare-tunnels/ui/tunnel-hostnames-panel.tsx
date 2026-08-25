"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Plus, Pencil, Trash2, ArrowRight, ExternalLink, Copy, Check } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { ConfirmDialog } from "@/shared/ui/confirm-dialog";
import { Can } from "@/entities/permission";
import { ACTIONS, PERMISSIONS } from "@/shared/constants/permissions";
import { useTunnelHostnamesQuery, useRemoveTunnelHostname } from "../hooks/use-tunnel-hostnames";
import { useCloudflareConfigQuery } from "@/entities/cloudflare-config";
import type { TunnelPublicHostname } from "../model/schema";
import { HostnameFormDialog } from "./hostname-form-dialog";
import { IconDns } from "@/shared/ui/icons";

export function TunnelHostnamesPanel({ environmentId, tunnelId }: { environmentId: string; tunnelId: string }) {
  const t = useTranslations("cloudflareTunnels");
  const { data: config } = useCloudflareConfigQuery(environmentId);
  const { data: hostnames = [], isLoading: hostnamesLoading } = useTunnelHostnamesQuery(environmentId, tunnelId, true);
  const removeHostname = useRemoveTunnelHostname(environmentId, tunnelId);

  const [formTarget, setFormTarget] = useState<TunnelPublicHostname | "create" | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<TunnelPublicHostname | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const handleCopy = (id: string, text: string) => {
    navigator.clipboard.writeText(`https://${text}`);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  return (
    <section className="flex flex-col gap-4 rounded-3xl border border-border/60 bg-gradient-to-br from-card via-card/90 to-blue-500/5 p-6 backdrop-blur-xl shadow-lg shadow-black/5 dark:shadow-black/20">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <IconDns className="size-8 shrink-0 rounded-xl shadow-xs" />
          <div>
            <h2 className="text-base font-bold tracking-tight text-foreground">
              {t("hostnames.title")}
            </h2>
            <p className="text-xs text-muted-foreground">
              {t("hostnames.subtitle")}
            </p>
          </div>
        </div>
        <Can I={ACTIONS.MANAGE} a={PERMISSIONS.CLOUDFLARE_ACCOUNT.RESOURCE}>
          <Button
            size="sm"
            onClick={() => setFormTarget("create")}
            className="gap-1.5 bg-gradient-to-r from-blue-600 to-indigo-600 font-semibold text-white shadow-md shadow-blue-500/20 hover:from-blue-700 hover:to-indigo-700 cursor-pointer"
          >
            <Plus className="size-3.5" aria-hidden="true" /> {t("hostnames.add")}
          </Button>
        </Can>
      </div>

      {hostnamesLoading ? (
        <div className="flex flex-col gap-3">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3.5 rounded-2xl border border-border/60 bg-card/60 p-4.5 animate-pulse">
            <div className="flex flex-col gap-2 w-full max-w-xs">
              <div className="h-4 w-44 rounded-md bg-muted/80" />
              <div className="h-3 w-32 rounded-md bg-muted/50" />
            </div>
            <div className="flex gap-2">
              <div className="size-8 rounded-xl bg-muted/60" />
              <div className="size-8 rounded-xl bg-muted/60" />
            </div>
          </div>
        </div>
      ) : hostnames.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-border/60 bg-muted/20 py-10 px-4 text-center">
          <IconDns className="size-12 rounded-2xl shadow-xs mb-3 opacity-90" />
          <p className="text-sm font-bold text-foreground">{t("hostnames.empty")}</p>
          <Can I={ACTIONS.MANAGE} a={PERMISSIONS.CLOUDFLARE_ACCOUNT.RESOURCE}>
            <Button
              size="sm"
              variant="outline"
              onClick={() => setFormTarget("create")}
              className="mt-4 gap-1.5 shadow-2xs cursor-pointer"
            >
              <Plus className="size-3.5" aria-hidden="true" /> {t("hostnames.add")}
            </Button>
          </Can>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {hostnames.map((hostname) => (
            <div
              key={hostname.id}
              className="flex flex-col sm:flex-row sm:items-center justify-between gap-3.5 rounded-2xl border border-border/60 bg-card/75 p-4.5 backdrop-blur-md transition-all hover:border-blue-500/40 hover:shadow-xs"
            >
              <div className="flex flex-col gap-1.5 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="inline-flex items-center rounded-md bg-blue-500/10 px-2 py-0.5 text-[11px] font-bold text-blue-600 dark:text-blue-400 border border-blue-500/20">
                    HTTPS
                  </span>
                  <span className="font-bold text-foreground text-sm font-mono">
                    {hostname.hostname}
                  </span>
                  <button
                    type="button"
                    onClick={() => handleCopy(hostname.id, hostname.hostname)}
                    aria-label={t("hostnames.copyLink")}
                    className="inline-flex items-center p-1 rounded-md text-muted-foreground/60 hover:text-foreground hover:bg-muted/80 transition-colors cursor-pointer"
                    title={t("hostnames.copyLink")}
                  >
                    {copiedId === hostname.id ? (
                      <span className="inline-flex items-center gap-1 text-[11px] font-medium text-emerald-600 dark:text-emerald-400">
                        <Check className="size-3.5" />
                        {t("hostnames.copied")}
                      </span>
                    ) : (
                      <Copy className="size-3.5" />
                    )}
                  </button>
                </div>
                <div className="flex items-center gap-2 text-xs font-mono text-muted-foreground">
                  <span className="text-muted-foreground/60">{t("hostnames.target")}:</span>
                  <span className="inline-flex items-center gap-1 rounded-md bg-muted/50 px-2 py-0.5 text-foreground font-semibold">
                    <ArrowRight className="size-3 text-primary" /> {hostname.service}
                  </span>
                </div>
              </div>
              <Can I={ACTIONS.MANAGE} a={PERMISSIONS.CLOUDFLARE_ACCOUNT.RESOURCE}>
                <div className="flex items-center gap-1 shrink-0 self-end sm:self-auto">
                  <button
                    type="button"
                    onClick={() => setFormTarget(hostname)}
                    aria-label={t("hostnames.edit")}
                    className="p-2 rounded-xl text-muted-foreground hover:text-foreground hover:bg-muted/80 transition-colors cursor-pointer"
                    title={t("hostnames.edit")}
                  >
                    <Pencil className="size-4" aria-hidden="true" />
                  </button>
                  <button
                    type="button"
                    onClick={() => setDeleteTarget(hostname)}
                    aria-label={t("hostnames.remove")}
                    className="p-2 rounded-xl text-muted-foreground hover:text-destructive hover:bg-rose-500/10 transition-colors cursor-pointer"
                    title={t("hostnames.remove")}
                  >
                    <Trash2 className="size-4" aria-hidden="true" />
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
          zoneName={config?.zoneName}
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
