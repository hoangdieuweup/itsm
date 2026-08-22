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

export function CloudflareAccountsPageContent() {
  const t = useTranslations("cloudflareAccounts");
  const { data: accounts } = useCloudflareAccountsQuery();
  const deleteAccount = useDeleteCloudflareAccount();

  const [formTarget, setFormTarget] = useState<CloudflareAccount | "create" | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<CloudflareAccount | null>(null);

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-foreground">{t("title")}</h1>
          <p className="text-sm text-muted-foreground">{t("description")}</p>
        </div>
        <Can I={ACTIONS.MANAGE} a={PERMISSIONS.CLOUDFLARE_ACCOUNT.RESOURCE}>
          <Button onClick={() => setFormTarget("create")}>
            <Plus className="size-4" aria-hidden="true" />
            {t("createAccount")}
          </Button>
        </Can>
      </div>

      {accounts.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-border py-16 text-center">
          <Cloud className="size-10 text-muted-foreground mb-3" aria-hidden="true" />
          <p className="text-sm text-muted-foreground">{t("empty")}</p>
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead className="bg-muted/50 text-left text-muted-foreground">
              <tr>
                <th className="px-4 py-3 font-medium">{t("table.label")}</th>
                <th className="px-4 py-3 font-medium">{t("table.cfAccountId")}</th>
                <th className="px-4 py-3 font-medium">{t("table.createdAt")}</th>
                <th className="px-4 py-3 font-medium text-right">{t("table.actions")}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {accounts.map((account) => (
                <tr key={account.id} className="hover:bg-muted/30">
                  <td className="px-4 py-3">
                    <Link
                      href={`${ROUTES.adminCloudflareAccounts}/${account.id}`}
                      className="font-medium text-foreground hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
                    >
                      {account.label}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">{account.cfAccountId}</td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {new Date(account.createdAt).toLocaleDateString()}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex justify-end gap-2">
                      <Can I={ACTIONS.MANAGE} a={PERMISSIONS.CLOUDFLARE_ACCOUNT.RESOURCE}>
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          onClick={() => setFormTarget(account)}
                          aria-label={t("editAccount")}
                        >
                          <Pencil className="size-4" aria-hidden="true" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          onClick={() => setDeleteTarget(account)}
                          aria-label={t("deleteConfirm.title")}
                        >
                          <Trash2 className="size-4 text-destructive" aria-hidden="true" />
                        </Button>
                      </Can>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {formTarget !== null && (
        <CloudflareAccountFormDialog
          account={formTarget === "create" ? null : formTarget}
          onClose={() => setFormTarget(null)}
        />
      )}

      {deleteTarget !== null && (
        <ConfirmDialog
          isOpen
          onClose={() => setDeleteTarget(null)}
          onConfirm={async () => {
            await deleteAccount.mutateAsync(deleteTarget.id);
            setDeleteTarget(null);
          }}
          title={t("deleteConfirm.title")}
          description={t("deleteConfirm.description")}
          variant="destructive"
          isLoading={deleteAccount.isPending}
        />
      )}
    </div>
  );
}
