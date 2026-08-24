"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Globe } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/input";
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

/** Splits an existing hostname into its subdomain part, given the environment's
 * bound zone. Falls back to the full hostname when it doesn't end with the
 * current zone (e.g. the zone changed since this hostname was created) — the
 * user can retype it under the now-required domain. */
function subdomainFor(hostname: string, zoneName: string): string {
  const suffix = `.${zoneName}`;
  return hostname.endsWith(suffix) ? hostname.slice(0, -suffix.length) : hostname;
}

export function HostnameFormDialog({
  environmentId,
  tunnelId,
  hostname,
  onClose,
}: {
  environmentId: string;
  tunnelId: string;
  hostname: TunnelPublicHostname | null;
  onClose: () => void;
}) {
  const t = useTranslations("cloudflareTunnels");
  const getErrorMessage = useApiErrorMessage("cloudflareTunnels");
  const { data: config, isLoading: configLoading } = useCloudflareConfigQuery(environmentId);
  const isEditing = hostname !== null;
  const addHostname = useAddTunnelHostname(environmentId, tunnelId);
  const updateHostname = useUpdateTunnelHostname(environmentId, tunnelId);
  const removeHostname = useRemoveTunnelHostname(environmentId, tunnelId);
  const [subdomain, setSubdomain] = useState(() =>
    hostname && config ? subdomainFor(hostname.hostname, config.zoneName) : (hostname?.hostname ?? ""),
  );
  const [service, setService] = useState(hostname?.service ?? "");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const isSaving = addHostname.isPending || updateHostname.isPending || removeHostname.isPending;
  const hostnameValue = config ? `${subdomain}.${config.zoneName}` : subdomain;

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    setErrorMessage(null);
    const onError = (err: unknown) => setErrorMessage(getErrorMessage(err));

    if (!isEditing) {
      addHostname.mutate({ hostname: hostnameValue, service }, { onSuccess: onClose, onError });
      return;
    }

    if (hostnameValue === hostname.hostname) {
      updateHostname.mutate({ hostnameId: hostname.id, service }, { onSuccess: onClose, onError });
      return;
    }

    // The backend has no rename-in-place endpoint (hostname is immutable on
    // TunnelPublicHostnameUpdate, matching Cloudflare's own PATCH constraints) —
    // change the hostname text itself by removing the old row and adding the new one.
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

  return (
    <Dialog
      icon={Globe}
      title={isEditing ? t("hostnames.editTitle") : t("hostnames.addTitle")}
      onClose={onClose}
      closeLabel={t("hostnames.cancel")}
    >
      <form onSubmit={handleSubmit} className="space-y-4 overflow-y-auto p-6">
        {errorMessage && <DialogErrorAlert message={errorMessage} />}

        {!configLoading && !config && <DialogErrorAlert message={t("hostnames.domainRequiresBinding")} />}

        <div className="space-y-1.5">
          <Label htmlFor="hostname-subdomain">{t("hostnames.subdomainLabel")}</Label>
          <div className="flex items-center gap-1.5">
            <Input
              id="hostname-subdomain"
              value={subdomain}
              onChange={(event) => setSubdomain(event.target.value)}
              disabled={configLoading || !config}
              required
              autoFocus={!isEditing}
              className="flex-1"
            />
            <span className="whitespace-nowrap text-sm text-muted-foreground">
              . {configLoading ? "…" : (config?.zoneName ?? "—")}
            </span>
          </div>
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="hostname-service">{t("hostnames.serviceLabel")}</Label>
          <Input
            id="hostname-service"
            value={service}
            onChange={(event) => setService(event.target.value)}
            placeholder="http://localhost:8080"
            required
            autoFocus={isEditing}
          />
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="outline" onClick={onClose}>
            {t("hostnames.cancel")}
          </Button>
          <Button type="submit" disabled={isSaving || configLoading || !config}>
            {isSaving ? t("hostnames.saving") : t("hostnames.save")}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
