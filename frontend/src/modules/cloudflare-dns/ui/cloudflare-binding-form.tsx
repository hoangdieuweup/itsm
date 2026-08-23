"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Cloud, Globe } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { Label } from "@/shared/ui/label";
import { useApiErrorMessage } from "@/shared/lib/handle-api-error";
import { useCloudflareAccountsQuery } from "@/entities/cloudflare-account";
import { useZonesQuery } from "../hooks/use-zones-query";
import { useCreateCloudflareConfig } from "../hooks/use-cloudflare-config";

export function CloudflareBindingForm({ environmentId }: { environmentId: string }) {
  const t = useTranslations("cloudflareDns");
  const getErrorMessage = useApiErrorMessage("cloudflareDns");
  const { data: accounts } = useCloudflareAccountsQuery();
  const [accountId, setAccountId] = useState<string | null>(null);
  const [zoneId, setZoneId] = useState<string>("");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const { data: zones, isFetching: zonesLoading } = useZonesQuery(accountId, accountId !== null);
  const createConfig = useCreateCloudflareConfig();

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!accountId || !zoneId) return;
    setErrorMessage(null);
    createConfig.mutate(
      { environmentId, cloudflareAccountId: accountId, zoneId },
      { onError: (err) => setErrorMessage(getErrorMessage(err)) },
    );
  };

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4 rounded-xl border bg-card p-5">
      <div className="flex items-center gap-2">
        <Cloud className="size-4 text-primary" aria-hidden="true" />
        <h2 className="text-sm font-bold text-foreground">{t("binding.title")}</h2>
      </div>
      <p className="text-sm text-muted-foreground">{t("binding.description")}</p>

      {errorMessage && (
        <div role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {errorMessage}
        </div>
      )}

      <div className="space-y-1.5">
        <Label htmlFor="binding-account">{t("binding.accountLabel")}</Label>
        <select
          id="binding-account"
          value={accountId ?? ""}
          onChange={(event) => {
            setAccountId(event.target.value || null);
            setZoneId("");
          }}
          className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          required
        >
          <option value="">{t("binding.selectAccount")}</option>
          {accounts.map((account) => (
            <option key={account.id} value={account.id}>
              {account.label}
            </option>
          ))}
        </select>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="binding-zone">{t("binding.zoneLabel")}</Label>
        <select
          id="binding-zone"
          value={zoneId}
          onChange={(event) => setZoneId(event.target.value)}
          disabled={accountId === null || zonesLoading}
          aria-describedby="binding-zone-hint"
          className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          required
        >
          <option value="">
            {accountId === null
              ? t("binding.selectAccountFirst")
              : zonesLoading
                ? t("binding.loadingZones")
                : t("binding.selectZone")}
          </option>
          {zones?.map((zone) => (
            <option key={zone.id} value={zone.id}>
              {zone.name}
            </option>
          ))}
        </select>
        <p id="binding-zone-hint" className="text-xs text-muted-foreground">
          {accountId === null ? t("binding.selectAccountFirst") : t("binding.zoneHint")}
        </p>
      </div>

      <Button type="submit" disabled={createConfig.isPending || !accountId || !zoneId} className="self-start">
        <Globe className="mr-1.5 size-3.5" aria-hidden="true" />
        {createConfig.isPending ? t("binding.binding") : t("binding.bind")}
      </Button>
    </form>
  );
}
