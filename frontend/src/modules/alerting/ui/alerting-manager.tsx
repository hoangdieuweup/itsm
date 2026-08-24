"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Bell, Plus, Pencil, Trash2 } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { ConfirmDialog } from "@/shared/ui/confirm-dialog";
import { Can } from "@/entities/permission";
import { ACTIONS, PERMISSIONS } from "@/shared/constants/permissions";
import { useEnvironmentQuery } from "@/entities/environment";
import { useAlertRulesQuery } from "../hooks/use-alert-rules";
import { useDeleteAlertRule } from "../hooks/use-delete-alert-rule";
import type { AlertRule } from "../model/schema";
import { AlertRuleFormDialog } from "./alert-rule-form-dialog";

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
      <section className="flex flex-col gap-3 rounded-xl border bg-card p-5">
        <div className="flex items-center justify-between">
          <h2 className="flex items-center gap-2 text-sm font-bold text-foreground">
            <Bell className="size-4 text-primary" aria-hidden="true" /> {t("title")}
          </h2>
          <Can I={ACTIONS.CREATE} a={PERMISSIONS.ALERT_RULE.RESOURCE}>
            <Button size="sm" onClick={() => setFormTarget("create")}>
              <Plus className="mr-1.5 size-3.5" aria-hidden="true" /> {t("addRule")}
            </Button>
          </Can>
        </div>

        {isLoading && <div className="h-24 w-full animate-pulse rounded-xl bg-muted/50" />}

        {!isLoading && rules.length === 0 && <p className="text-sm text-muted-foreground">{t("empty")}</p>}

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
                      <Can I={ACTIONS.UPDATE} a={PERMISSIONS.ALERT_RULE.RESOURCE}>
                        <div className="flex justify-end gap-2">
                          <button
                            type="button"
                            onClick={() => setFormTarget(rule)}
                            aria-label={t("table.editRule")}
                            className="cursor-pointer text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                          >
                            <Pencil className="size-3.5" aria-hidden="true" />
                          </button>
                          <Can I={ACTIONS.DELETE} a={PERMISSIONS.ALERT_RULE.RESOURCE}>
                            <button
                              type="button"
                              onClick={() => setDeleteTarget(rule)}
                              aria-label={t("table.deleteRule")}
                              className="cursor-pointer text-muted-foreground hover:text-destructive focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                            >
                              <Trash2 className="size-3.5" aria-hidden="true" />
                            </button>
                          </Can>
                        </div>
                      </Can>
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
