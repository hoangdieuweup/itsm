"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Cloud, ShieldCheck, ShieldAlert, Eye, EyeOff, UserPlus, Trash2, Copy } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { ConfirmDialog } from "@/shared/ui/confirm-dialog";
import { Can } from "@/entities/permission";
import { PERMISSIONS } from "@/shared/constants/permissions";
import { useApiErrorMessage } from "@/shared/lib/handle-api-error";
import { useCloudflareAccountQuery } from "@/entities/cloudflare-account";
import { useTestCloudflareAccountConnection } from "../hooks/use-test-cloudflare-account-connection";
import { useRevealCloudflareAccountToken } from "../hooks/use-reveal-cloudflare-account-token";
import { useCloudflareAccountManagersQuery } from "../hooks/use-cloudflare-account-managers";
import { useRemoveCloudflareAccountManager } from "../hooks/use-remove-cloudflare-account-manager";
import { CloudflareAccountManagerFormDialog } from "./cloudflare-account-manager-form-dialog";

interface CloudflareAccountDetailViewProps {
  accountId: string;
}

export function CloudflareAccountDetailView({ accountId }: CloudflareAccountDetailViewProps) {
  const t = useTranslations("cloudflareAccounts");
  const getErrorMessage = useApiErrorMessage("cloudflareAccounts");
  const { data: account } = useCloudflareAccountQuery(accountId);
  const { data: managers } = useCloudflareAccountManagersQuery(accountId);

  const testConnection = useTestCloudflareAccountConnection();
  const revealToken = useRevealCloudflareAccountToken();
  const removeManager = useRemoveCloudflareAccountManager(accountId);

  const [revealedToken, setRevealedToken] = useState<string | null>(null);
  const [assignOpen, setAssignOpen] = useState(false);
  const [removeTarget, setRemoveTarget] = useState<string | null>(null);

  return (
    <div className="p-6 space-y-6">
      <section className="rounded-lg border border-border p-5">
        <div className="flex items-center gap-2 mb-4">
          <Cloud className="size-5 text-primary" aria-hidden="true" />
          <h2 className="text-lg font-semibold">{account.label}</h2>
        </div>
        <dl className="grid grid-cols-2 gap-4 text-sm mb-4">
          <div>
            <dt className="text-muted-foreground">{t("table.cfAccountId")}</dt>
            <dd className="font-medium">{account.cfAccountId}</dd>
          </div>
        </dl>
        <div className="flex flex-wrap gap-2">
          <Can I="view" a={PERMISSIONS.CLOUDFLARE_ACCOUNT.RESOURCE}>
            <Button
              variant="outline"
              size="sm"
              onClick={() => testConnection.mutate(accountId)}
              disabled={testConnection.isPending}
            >
              <ShieldCheck className="size-4" aria-hidden="true" />
              {t("actions.testConnection")}
            </Button>
          </Can>
          <Can I="manage" a={PERMISSIONS.CLOUDFLARE_ACCOUNT.RESOURCE}>
            <Button
              variant="outline"
              size="sm"
              onClick={async () => {
                if (revealedToken) {
                  setRevealedToken(null);
                  return;
                }
                const token = await revealToken.mutateAsync(accountId);
                setRevealedToken(token);
              }}
              disabled={revealToken.isPending}
              aria-pressed={Boolean(revealedToken)}
            >
              {revealedToken ? (
                <EyeOff className="size-4" aria-hidden="true" />
              ) : (
                <Eye className="size-4" aria-hidden="true" />
              )}
              {revealedToken ? t("actions.hideToken") : t("actions.revealToken")}
            </Button>
          </Can>
        </div>

        {testConnection.isSuccess && (
          <p className="mt-2 flex items-center gap-1.5 text-sm text-emerald-600 dark:text-emerald-400">
            <ShieldCheck className="size-4" aria-hidden="true" />
            {t("actions.testConnectionSuccess")}
          </p>
        )}
        {testConnection.isError && (
          <p role="alert" className="mt-2 flex items-center gap-1.5 text-sm text-destructive">
            <ShieldAlert className="size-4" aria-hidden="true" />
            {getErrorMessage(testConnection.error)}
          </p>
        )}

        {revealedToken && (
          <div
            role="status"
            className="mt-3 flex items-center justify-between gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2"
          >
            <code className="text-xs break-all">{revealedToken}</code>
            <Button
              variant="ghost"
              size="icon-xs"
              onClick={() => navigator.clipboard.writeText(revealedToken)}
              aria-label={t("actions.copyToken")}
            >
              <Copy className="size-4" aria-hidden="true" />
            </Button>
          </div>
        )}
      </section>

      <section className="rounded-lg border border-border p-5">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-base font-semibold">{t("managers.title")}</h3>
          <Can I="manage" a={PERMISSIONS.CLOUDFLARE_ACCOUNT.RESOURCE}>
            <Button variant="outline" size="sm" onClick={() => setAssignOpen(true)}>
              <UserPlus className="size-4" aria-hidden="true" />
              {t("managers.assign")}
            </Button>
          </Can>
        </div>

        {managers.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("managers.empty")}</p>
        ) : (
          <ul className="divide-y divide-border">
            {managers.map((manager) => (
              <li key={manager.userId} className="flex items-center justify-between py-2 text-sm">
                <div>
                  <p className="font-medium">{manager.name}</p>
                  <p className="text-muted-foreground">{manager.email}</p>
                </div>
                <div className="flex items-center gap-3">
                  <span className="text-xs uppercase text-muted-foreground">
                    {t(`managers.levels.${manager.accessLevel}`)}
                  </span>
                  <Can I="manage" a={PERMISSIONS.CLOUDFLARE_ACCOUNT.RESOURCE}>
                    <Button
                      variant="ghost"
                      size="icon-xs"
                      onClick={() => setRemoveTarget(manager.userId)}
                      aria-label={t("managers.removeConfirm.title")}
                    >
                      <Trash2 className="size-4 text-destructive" aria-hidden="true" />
                    </Button>
                  </Can>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      {assignOpen && (
        <CloudflareAccountManagerFormDialog accountId={accountId} onClose={() => setAssignOpen(false)} />
      )}

      {removeTarget !== null && (
        <ConfirmDialog
          isOpen
          onClose={() => setRemoveTarget(null)}
          onConfirm={async () => {
            await removeManager.mutateAsync(removeTarget);
            setRemoveTarget(null);
          }}
          title={t("managers.removeConfirm.title")}
          description={t("managers.removeConfirm.description")}
          variant="destructive"
          isLoading={removeManager.isPending}
        />
      )}
    </div>
  );
}
