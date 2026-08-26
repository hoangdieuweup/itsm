"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Link } from "@/shared/lib/i18n/navigation";
import { Plus, Pencil, Trash2, Cloud } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { ConfirmDialog } from "@/shared/ui/confirm-dialog";
import { Can } from "@/entities/permission";
import { ROUTES } from "@/shared/constants/routes";
import { ACTIONS, PERMISSIONS } from "@/shared/constants/permissions";
import { useCloudflareAccountsQuery, type CloudflareAccount } from "@/entities/cloudflare-account";
import { useDeleteCloudflareAccount } from "../hooks/use-delete-cloudflare-account";
import { CloudflareAccountFormDialog } from "./cloudflare-account-form-dialog";

import { m } from "@/shared/lib/motion";

export function CloudflareAccountsPageContent() {
  const t = useTranslations("cloudflareAccounts");
  const { data: accounts } = useCloudflareAccountsQuery();
  const deleteAccount = useDeleteCloudflareAccount();

  const [formTarget, setFormTarget] = useState<CloudflareAccount | "create" | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<CloudflareAccount | null>(null);

  return (
    <m.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="flex flex-1 min-h-0 flex-col gap-4"
    >
      <div className="shrink-0 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-2xl font-extrabold tracking-tight text-foreground sm:text-3xl">
              {t("title")}
            </h1>
            <span className="inline-flex items-center rounded-full border border-blue-500/30 bg-blue-500/15 px-2.5 py-0.5 font-mono text-xs font-bold text-blue-600 dark:text-blue-400">
              {accounts.length}
            </span>
          </div>
          <p className="mt-1 text-sm text-muted-foreground">{t("description")}</p>
        </div>

        <Can I={ACTIONS.CREATE} a={PERMISSIONS.CLOUDFLARE_ACCOUNT.RESOURCE}>
          <Button
            onClick={() => setFormTarget("create")}
            className="gap-2 self-start bg-gradient-to-r from-blue-600 to-cyan-600 font-semibold text-white shadow-md shadow-blue-500/25 hover:from-blue-700 hover:to-cyan-700 sm:self-auto"
          >
            <Plus className="size-4" aria-hidden="true" />
            {t("createAccount")}
          </Button>
        </Can>
      </div>

      {accounts.length === 0 ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-3 rounded-3xl border border-border/50 bg-card/75 py-16 text-center backdrop-blur-xl shadow-lg">
          <div className="flex size-12 items-center justify-center rounded-2xl bg-blue-500/10 text-blue-600 dark:text-blue-400">
            <Cloud className="size-6" aria-hidden="true" />
          </div>
          <h2 className="text-lg font-bold text-foreground">{t("emptyTitle")}</h2>
          <p className="max-w-sm text-sm text-muted-foreground">{t("empty")}</p>
        </div>
      ) : (
        <div className="flex flex-1 min-h-0 flex-col overflow-hidden rounded-3xl border border-border/50 bg-card/75 backdrop-blur-xl shadow-lg shadow-black/5 dark:shadow-black/20">
          <div className="flex-1 overflow-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 z-10 border-b border-border/40 bg-card/95 backdrop-blur-md text-left text-[11px] font-bold uppercase tracking-wider text-muted-foreground/90">
              <tr>
                <th className="px-6 py-4 font-bold text-foreground/80">{t("table.label")}</th>
                <th className="px-6 py-4 font-bold text-foreground/80">{t("table.cfAccountId")}</th>
                <th className="px-6 py-4 font-bold text-foreground/80">{t("table.createdAt")}</th>
                <th className="px-6 py-4 text-right font-bold text-foreground/80">{t("table.actions")}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/40">
              {accounts.map((account) => (
                <tr key={account.id} className="transition-colors hover:bg-muted/40">
                  <td className="px-6 py-4 font-semibold text-foreground">
                    <Link
                      href={`${ROUTES.adminCloudflareAccounts}/${account.id}`}
                      className="text-primary hover:underline"
                    >
                      {account.label}
                    </Link>
                  </td>
                  <td className="px-6 py-4 font-mono text-xs text-muted-foreground">
                    {account.cfAccountId}
                  </td>
                  <td className="px-6 py-4 font-mono text-xs text-muted-foreground">
                    {new Date(account.createdAt).toLocaleDateString()}
                  </td>
                  <td className="px-6 py-4 text-right">
                    <div className="flex justify-end gap-1.5">
                      <Can I={ACTIONS.DELETE} a={PERMISSIONS.CLOUDFLARE_ACCOUNT.RESOURCE}>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setFormTarget(account)}
                          className="size-8 p-0 text-muted-foreground hover:text-foreground"
                          aria-label={t("editAccount")}
                        >
                          <Pencil className="size-3.5" aria-hidden="true" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setDeleteTarget(account)}
                          className="size-8 p-0 text-rose-600 hover:bg-rose-500/10 hover:text-rose-700 dark:hover:bg-rose-950/50"
                          aria-label={t("deleteConfirm.title")}
                        >
                          <Trash2 className="size-3.5" aria-hidden="true" />
                        </Button>
                      </Can>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      )}

      {formTarget !== null && (
        <CloudflareAccountFormDialog
          account={formTarget === "create" ? null : formTarget}
          onClose={() => setFormTarget(null)}
        />
      )}

      <ConfirmDialog
        isOpen={deleteTarget !== null}
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => {
          if (deleteTarget) {
            deleteAccount.mutate(deleteTarget.id, { onSuccess: () => setDeleteTarget(null) });
          }
        }}
        title={t("deleteConfirm.title")}
        description={t("deleteConfirm.description", { label: deleteTarget?.label ?? "" })}
        isLoading={deleteAccount.isPending}
      />
    </m.div>
  );
}
