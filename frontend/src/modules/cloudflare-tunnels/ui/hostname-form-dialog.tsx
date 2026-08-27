"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Button } from "@/shared/ui/button";
import { Label } from "@/shared/ui/label";
import { Dialog, DialogErrorAlert } from "@/shared/ui/dialog";
import { useApiErrorMessage } from "@/shared/lib/handle-api-error";
import { useCloudflareConfigQuery } from "@/entities/cloudflare-config";
import {
  useAddTunnelHostname,
  useRemoveTunnelHostname,
  useUpdateTunnelHostname,
} from "../hooks/use-tunnel-hostnames";
import type { TunnelPublicHostname } from "../model/schema";
import { IconDns } from "@/shared/ui/icons";

function subdomainFor(hostname: string, zoneName: string): string {
  const suffix = `.${zoneName}`;
  return hostname.endsWith(suffix) ? hostname.slice(0, -suffix.length) : hostname;
}

/**
 * Subdomain the form starts from, derived during render.
 *
 * The zone name can arrive after mount (it comes from `useCloudflareConfigQuery`),
 * so this is recomputed rather than synced into state by an effect — see
 * https://react.dev/learn/you-might-not-need-an-effect.
 */
function initialSubdomainFor(
  hostname: TunnelPublicHostname | null,
  zoneName: string | undefined,
): string {
  if (!hostname) return "";
  return zoneName ? subdomainFor(hostname.hostname, zoneName) : hostname.hostname;
}

function useHostnameFormSubmit({
  environmentId,
  tunnelId,
  hostname,
  hostnameValue,
  service,
  onClose,
}: {
  environmentId: string;
  tunnelId: string;
  hostname: TunnelPublicHostname | null;
  hostnameValue: string;
  service: string;
  onClose: () => void;
}) {
  const t = useTranslations("cloudflareTunnels");
  const getErrorMessage = useApiErrorMessage("cloudflareTunnels");
  const addHostname = useAddTunnelHostname(environmentId, tunnelId);
  const updateHostname = useUpdateTunnelHostname(environmentId, tunnelId);
  const removeHostname = useRemoveTunnelHostname(environmentId, tunnelId);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    setErrorMessage(null);
    const onError = (err: unknown) => setErrorMessage(getErrorMessage(err));

    if (hostname === null) {
      addHostname.mutate({ hostname: hostnameValue, service }, { onSuccess: onClose, onError });
      return;
    }
    if (hostnameValue === hostname.hostname) {
      updateHostname.mutate({ hostnameId: hostname.id, service }, { onSuccess: onClose, onError });
      return;
    }
    removeHostname.mutate(hostname.id, {
      onSuccess: () => {
        addHostname.mutate(
          { hostname: hostnameValue, service },
          {
            onSuccess: onClose,
            onError: (err: unknown) =>
              setErrorMessage(t("hostnames.renameFailedAfterRemove", { error: getErrorMessage(err) })),
          },
        );
      },
      onError,
    });
  };

  return {
    submit,
    errorMessage,
    isSaving: addHostname.isPending || updateHostname.isPending || removeHostname.isPending,
  };
}

function SubdomainField({
  value,
  onChange,
  zoneName,
  configLoading,
  disabled,
  autoFocus,
}: {
  value: string;
  onChange: (next: string) => void;
  zoneName: string | undefined;
  configLoading: boolean;
  disabled: boolean;
  autoFocus: boolean;
}) {
  const t = useTranslations("cloudflareTunnels");
  const loadingSuffix = configLoading ? "…" : "—";

  return (
    <div className="space-y-2">
      <Label htmlFor="hostname-subdomain" className="text-xs font-semibold text-foreground">
        {t("hostnames.subdomainLabel")}
      </Label>
      <div className="group flex h-11 w-full items-center rounded-xl border border-input bg-muted/20 px-3.5 shadow-xs transition-all focus-within:border-primary/60 focus-within:bg-background focus-within:ring-2 focus-within:ring-primary/20">
        <input
          id="hostname-subdomain"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          disabled={disabled}
          required
          placeholder="e.g. app, api, staging"
          autoFocus={autoFocus}
          className="flex-1 bg-transparent font-mono text-sm text-foreground outline-none placeholder:text-muted-foreground/40 disabled:cursor-not-allowed disabled:opacity-50"
        />
        <span className="shrink-0 select-none pl-1 font-mono text-sm font-medium text-muted-foreground/70">
          .{zoneName ?? loadingSuffix}
        </span>
      </div>

      {value && zoneName && (
        <div className="flex items-center gap-2 rounded-xl bg-blue-500/10 border border-blue-500/20 px-3.5 py-2 text-xs font-mono text-blue-600 dark:text-blue-400">
          <span className="font-bold">{t("hostnames.publicUrl")}:</span>
          <span className="text-foreground select-all">https://{value}.{zoneName}</span>
        </div>
      )}
    </div>
  );
}

function ServiceField({
  value,
  onChange,
  autoFocus,
}: {
  value: string;
  onChange: (next: string) => void;
  autoFocus: boolean;
}) {
  const t = useTranslations("cloudflareTunnels");

  return (
    <div className="space-y-2">
      <Label htmlFor="hostname-service" className="text-xs font-semibold text-foreground">
        {t("hostnames.serviceLabel")}
      </Label>
      <div className="group flex h-11 w-full items-center rounded-xl border border-input bg-muted/20 px-3.5 shadow-xs transition-all focus-within:border-primary/60 focus-within:bg-background focus-within:ring-2 focus-within:ring-primary/20">
        <input
          id="hostname-service"
          value={value}
          onChange={(event) => onChange(event.target.value)}
          placeholder="http://localhost:8080"
          required
          autoFocus={autoFocus}
          className="w-full bg-transparent font-mono text-sm text-foreground outline-none placeholder:text-muted-foreground/40"
        />
      </div>
      <p className="text-[11px] text-muted-foreground">
        {t("hostnames.serviceHint")}
      </p>
    </div>
  );
}

function HostnameFormActions({
  isSaving,
  isBound,
  onClose,
}: {
  isSaving: boolean;
  isBound: boolean;
  onClose: () => void;
}) {
  const t = useTranslations("cloudflareTunnels");

  return (
    <div className="flex justify-end gap-2.5 pt-3">
      <Button type="button" variant="outline" onClick={onClose} className="rounded-xl cursor-pointer">
        {t("hostnames.cancel")}
      </Button>
      <Button
        type="submit"
        disabled={isSaving || !isBound}
        className="rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 font-semibold text-white shadow-md shadow-blue-500/20 hover:from-blue-700 hover:to-indigo-700 cursor-pointer"
      >
        {isSaving ? t("hostnames.saving") : t("hostnames.save")}
      </Button>
    </div>
  );
}

export function HostnameFormDialog({
  environmentId,
  tunnelId,
  hostname,
  zoneName: initialZoneName,
  onClose,
}: {
  environmentId: string;
  tunnelId: string;
  hostname: TunnelPublicHostname | null;
  zoneName?: string;
  onClose: () => void;
}) {
  const t = useTranslations("cloudflareTunnels");
  const { data: config, isLoading: configLoading } = useCloudflareConfigQuery(environmentId);
  const effectiveZoneName = initialZoneName ?? config?.zoneName;
  const isEditing = hostname !== null;
  const isBound = Boolean(effectiveZoneName) || (!configLoading && config !== undefined);

  // `null` means "untouched" — the field then tracks the derived initial value,
  // which settles once the zone name loads.
  const [editedSubdomain, setEditedSubdomain] = useState<string | null>(null);
  const subdomain = editedSubdomain ?? initialSubdomainFor(hostname, effectiveZoneName);
  const [service, setService] = useState(hostname?.service ?? "");
  const hostnameValue = effectiveZoneName ? `${subdomain}.${effectiveZoneName}` : subdomain;

  const { submit, errorMessage, isSaving } = useHostnameFormSubmit({
    environmentId,
    tunnelId,
    hostname,
    hostnameValue,
    service,
    onClose,
  });

  return (
    <Dialog
      icon={IconDns}
      title={isEditing ? t("hostnames.editTitle") : t("hostnames.addTitle")}
      onClose={onClose}
      closeLabel={t("hostnames.cancel")}
    >
      <form onSubmit={submit} className="space-y-5 overflow-y-auto p-6">
        {errorMessage && <DialogErrorAlert message={errorMessage} />}
        {!isBound && !configLoading && <DialogErrorAlert message={t("hostnames.domainRequiresBinding")} />}

        <SubdomainField
          value={subdomain}
          onChange={setEditedSubdomain}
          zoneName={effectiveZoneName}
          configLoading={configLoading}
          disabled={!isBound}
          autoFocus={!isEditing}
        />

        <ServiceField value={service} onChange={setService} autoFocus={isEditing} />

        <HostnameFormActions isSaving={isSaving} isBound={isBound} onClose={onClose} />
      </form>
    </Dialog>
  );
}
