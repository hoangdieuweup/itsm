"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Pencil, Plus, Trash2, Globe, KeyRound, Clock, Terminal } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { ConfirmDialog } from "@/shared/ui/confirm-dialog";
import { CanInProject } from "@/entities/permission";
import { ACTIONS, RESOURCES } from "@/shared/constants/permissions";
import { useLokiConfigQuery } from "@/entities/loki-config";
import { useDeleteLokiConfig } from "../hooks/use-loki-config";
import { LokiConfigFormDialog } from "./loki-config-form-dialog";
import { IconGrafana } from "@/shared/ui/icons";

/**
 * Loki configuration management surface — shows current config status with
 * options to create, edit, or delete. Rendered inside a Drawer from the
 * environment card on Project Detail. Follows the same visual language as
 * TunnelsManager and AlertingManager.
 */
export function LokiManager({ environmentId }: { environmentId: string }) {
  const t = useTranslations("logViewer");
  const { data: config, isLoading } = useLokiConfigQuery(environmentId);
  const deleteMutation = useDeleteLokiConfig(environmentId);

  const [formTarget, setFormTarget] = useState<"create" | "edit" | null>(null);
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);

  return (
    <div className="flex flex-1 flex-col gap-6">
      <section className="flex flex-col gap-4 rounded-3xl border border-border/60 bg-gradient-to-br from-card via-card/90 to-purple-500/5 p-6 backdrop-blur-xl shadow-lg shadow-black/5 dark:shadow-black/20">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <IconGrafana className="size-8 shrink-0 rounded-xl shadow-xs" />
            <div>
              <h2 className="text-base font-bold tracking-tight text-foreground">
                {t("config.title")}
              </h2>
              <p className="text-xs text-muted-foreground">
                {t("config.description")}
              </p>
            </div>
          </div>
          {config && (
            <CanInProject I={ACTIONS.MANAGE} a={RESOURCES.PROJECT_LOKI_CONFIG}>
              <Button
                size="sm"
                onClick={() => setFormTarget("edit")}
                className="gap-1.5 bg-gradient-to-r from-purple-600 to-violet-600 font-semibold text-white shadow-md shadow-purple-500/20 hover:from-purple-700 hover:to-violet-700 cursor-pointer"
              >
                <Pencil className="size-3.5" aria-hidden="true" /> {t("config.edit")}
              </Button>
            </CanInProject>
          )}
        </div>

        {isLoading && <div className="h-28 w-full animate-pulse rounded-2xl bg-muted/50" />}

        {!isLoading && !config && (
          <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-border/60 bg-muted/20 py-10 px-4 text-center">
            <IconGrafana className="size-12 rounded-2xl shadow-xs mb-3 opacity-90" />
            <h3 className="text-sm font-bold text-foreground">
              {t("config.noSourceConfigured")}
            </h3>
            <p className="text-xs text-muted-foreground mt-1 max-w-sm">
              {t("config.description")}
            </p>
            <CanInProject I={ACTIONS.MANAGE} a={RESOURCES.PROJECT_LOKI_CONFIG}>
              <Button
                size="sm"
                variant="outline"
                onClick={() => setFormTarget("create")}
                className="mt-4 gap-1.5 shadow-2xs cursor-pointer"
              >
                <Plus className="size-3.5" aria-hidden="true" /> {t("config.configure")}
              </Button>
            </CanInProject>
          </div>
        )}

        {!isLoading && config && (
          <>
            <div className="flex flex-col gap-3 rounded-2xl border border-border/50 bg-card/75 p-5 backdrop-blur-md">
              {/* Endpoint URL */}
              <div className="flex items-start gap-3">
                <div className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-purple-500/10 text-purple-600 dark:text-purple-400">
                  <Globe className="size-4" aria-hidden="true" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
                    {t("config.endpointUrl")}
                  </p>
                  <p className="mt-0.5 break-all font-mono text-xs text-foreground">
                    {config.endpointUrl}
                  </p>
                </div>
              </div>

              {/* Tenant ID */}
              {config.tenantId && (
                <div className="flex items-start gap-3 border-t border-border/30 pt-3">
                  <div className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-blue-500/10 text-blue-600 dark:text-blue-400">
                    <Terminal className="size-4" aria-hidden="true" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
                      {t("config.tenantId")}
                    </p>
                    <p className="mt-0.5 font-mono text-xs text-foreground">
                      {config.tenantId}
                    </p>
                  </div>
                </div>
              )}

              {/* Auth Type */}
              <div className="flex items-start gap-3 border-t border-border/30 pt-3">
                <div className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
                  <KeyRound className="size-4" aria-hidden="true" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
                    {t("config.authType")}
                  </p>
                  <span className="mt-0.5 inline-flex items-center gap-1.5 rounded-full border border-emerald-500/30 bg-emerald-500/15 px-2.5 py-0.5 text-[10px] font-bold text-emerald-600 uppercase dark:text-emerald-400">
                    {t(`config.authType${config.authType.charAt(0).toUpperCase()}${config.authType.slice(1)}`)}
                  </span>
                </div>
              </div>

              {/* Default Query */}
              {config.defaultQuery && (
                <div className="flex items-start gap-3 border-t border-border/30 pt-3">
                  <div className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-amber-500/10 text-amber-600 dark:text-amber-400">
                    <Terminal className="size-4" aria-hidden="true" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
                      {t("config.defaultQuery")}
                    </p>
                    <p className="mt-0.5 break-all rounded-lg bg-muted/40 px-2.5 py-1.5 font-mono text-xs text-foreground">
                      {config.defaultQuery}
                    </p>
                  </div>
                </div>
              )}

              {/* Default Range */}
              <div className="flex items-start gap-3 border-t border-border/30 pt-3">
                <div className="flex size-8 shrink-0 items-center justify-center rounded-lg bg-rose-500/10 text-rose-600 dark:text-rose-400">
                  <Clock className="size-4" aria-hidden="true" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-[11px] font-bold uppercase tracking-wider text-muted-foreground">
                    {t("config.defaultRangeMinutes")}
                  </p>
                  <p className="mt-0.5 text-sm font-semibold text-foreground">
                    {config.defaultRangeMinutes} min
                  </p>
                </div>
              </div>
            </div>

            <CanInProject I={ACTIONS.MANAGE} a={RESOURCES.PROJECT_LOKI_CONFIG}>
              <div className="flex items-center justify-end gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setDeleteConfirmOpen(true)}
                  className="gap-1.5 text-destructive hover:bg-destructive/10 cursor-pointer"
                >
                  <Trash2 className="size-3.5" aria-hidden="true" /> {t("config.delete")}
                </Button>
              </div>
            </CanInProject>
          </>
        )}
      </section>

      {formTarget !== null && (
        <LokiConfigFormDialog
          environmentId={environmentId}
          config={formTarget === "edit" ? (config ?? null) : null}
          onClose={() => setFormTarget(null)}
        />
      )}
      <ConfirmDialog
        isOpen={deleteConfirmOpen}
        onClose={() => setDeleteConfirmOpen(false)}
        onConfirm={() => {
          deleteMutation.mutate(undefined, {
            onSuccess: () => setDeleteConfirmOpen(false),
          });
        }}
        title={t("config.deleteConfirm.title")}
        description={t("config.deleteConfirm.description")}
        variant="destructive"
        isLoading={deleteMutation.isPending}
      />
    </div>
  );
}
