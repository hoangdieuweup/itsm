"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Plus, Pencil, Trash2 } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { Skeleton } from "@/shared/ui/skeleton";
import { ConfirmDialog } from "@/shared/ui/confirm-dialog";
import { CanInProject } from "@/entities/permission";
import { ACTIONS, PERMISSIONS } from "@/shared/constants/permissions";
import { useEnvironmentQuery } from "@/entities/environment";
import { useAlertRulesQuery } from "../hooks/use-alert-rules";
import { useDeleteAlertRule } from "../hooks/use-delete-alert-rule";
import type { AlertRule } from "../model/schema";
import { AlertRuleFormDialog } from "./alert-rule-form-dialog";
import { IconNotification } from "@/shared/ui/icons";

/**
 * The reusable alert-rule-management surface — table, create/edit/delete —
 * with no page-level chrome of its own. Shared by the full-page route
 * (`AlertingPageContent`, which adds the `<h1>`/padding wrapper) and the
 * inline drawer opened from the environment chip on Project Detail.
 */
export function AlertingManager({ environmentId }: { environmentId: string }) {
  const t = useTranslations("alerting");
  const { data: environment } = useEnvironmentQuery(environmentId);
  const { data: rules = [], isLoading } = useAlertRulesQuery(environmentId);
  const deleteRule = useDeleteAlertRule(environmentId);

  const [formTarget, setFormTarget] = useState<AlertRule | "create" | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<AlertRule | null>(null);

  return (
    <div className="flex flex-1 flex-col gap-6">
      <section className="flex flex-col gap-4 rounded-3xl border border-border/60 bg-gradient-to-br from-card via-card/90 to-amber-500/5 p-6 backdrop-blur-xl shadow-lg shadow-black/5 dark:shadow-black/20">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <IconNotification className="size-8 shrink-0 rounded-xl shadow-xs" />
            <div>
              <h2 className="text-base font-bold tracking-tight text-foreground">
                {t("title")}
              </h2>
              <p className="text-xs text-muted-foreground">
                Automated incident triggers & multi-channel routing
              </p>
            </div>
          </div>
          <CanInProject I={ACTIONS.CREATE} a={PERMISSIONS.PROJECT_ALERT_RULE.RESOURCE}>
            <Button
              size="sm"
              onClick={() => setFormTarget("create")}
              className="gap-1.5 bg-gradient-to-r from-amber-600 to-orange-600 font-semibold text-white shadow-md shadow-amber-500/20 hover:from-amber-700 hover:to-orange-700 cursor-pointer"
            >
              <Plus className="size-3.5" aria-hidden="true" /> {t("addRule")}
            </Button>
          </CanInProject>
        </div>

        {isLoading && <Skeleton className="h-28 w-full rounded-2xl" />}

        {!isLoading && rules.length === 0 && (
          <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-border/60 bg-muted/20 py-10 px-4 text-center">
            <IconNotification className="size-12 rounded-2xl shadow-xs mb-3 opacity-90" />
            <h3 className="text-sm font-bold text-foreground">
              {t("empty")}
            </h3>
            <p className="text-xs text-muted-foreground mt-1 max-w-sm">
              Define metric thresholds and LogQL conditions to trigger automated alerts across Telegram, Discord & Slack.
            </p>
            <CanInProject I={ACTIONS.CREATE} a={PERMISSIONS.PROJECT_ALERT_RULE.RESOURCE}>
              <Button
                size="sm"
                variant="outline"
                onClick={() => setFormTarget("create")}
                className="mt-4 gap-1.5 shadow-2xs cursor-pointer"
              >
                <Plus className="size-3.5" aria-hidden="true" /> {t("addRule")}
              </Button>
            </CanInProject>
          </div>
        )}

        {!isLoading && rules.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b text-left text-xs uppercase text-muted-foreground">
                  <th className="py-2 pr-4">{t("table.name")}</th>
                  <th className="py-2 pr-4">{t("table.source")}</th>
                  <th className="py-2 pr-4">{t("table.severity")}</th>
                  <th className="py-2 pr-4">{t("table.status")}</th>
                  <th className="py-2" />
                </tr>
              </thead>
              <tbody className="divide-y">
                {rules.map((rule) => (
                  <tr key={rule.id}>
                    <td className="py-2 pr-4">{rule.name}</td>
                    <td className="py-2 pr-4 text-muted-foreground">{t(`sources.${rule.source}`)}</td>
                    <td className="py-2 pr-4 text-muted-foreground">{t(`severities.${rule.severity}`)}</td>
                    <td className="py-2 pr-4">
                      <span className="text-xs text-muted-foreground">
                        {rule.isActive ? t("table.active") : t("table.inactive")}
                      </span>
                    </td>
                    <td className="py-2 text-right">
                      <CanInProject I={ACTIONS.UPDATE} a={PERMISSIONS.PROJECT_ALERT_RULE.RESOURCE}>
                        <div className="flex justify-end gap-2">
                          <button
                            type="button"
                            onClick={() => setFormTarget(rule)}
                            aria-label={t("table.editRule")}
                            className="cursor-pointer text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                          >
                            <Pencil className="size-3.5" aria-hidden="true" />
                          </button>
                          <CanInProject I={ACTIONS.DELETE} a={PERMISSIONS.PROJECT_ALERT_RULE.RESOURCE}>
                            <button
                              type="button"
                              onClick={() => setDeleteTarget(rule)}
                              aria-label={t("table.deleteRule")}
                              className="cursor-pointer text-muted-foreground hover:text-destructive focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                            >
                              <Trash2 className="size-3.5" aria-hidden="true" />
                            </button>
                          </CanInProject>
                        </div>
                      </CanInProject>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {formTarget !== null && (
        <AlertRuleFormDialog
          environmentId={environmentId}
          projectId={environment.projectId}
          alertRule={formTarget === "create" ? null : formTarget}
          onClose={() => setFormTarget(null)}
        />
      )}

      <ConfirmDialog
        isOpen={deleteTarget !== null}
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => {
          if (deleteTarget) {
            deleteRule.mutate(deleteTarget.id, { onSuccess: () => setDeleteTarget(null) });
          }
        }}
        title={t("deleteConfirm.title")}
        description={t("deleteConfirm.description", { name: deleteTarget?.name ?? "" })}
        variant="destructive"
        isLoading={deleteRule.isPending}
      />
    </div>
  );
}
