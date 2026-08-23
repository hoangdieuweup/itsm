"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Globe } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/input";
import { Label } from "@/shared/ui/label";
import { Dialog, DialogErrorAlert } from "@/shared/ui/dialog";
import { useApiErrorMessage } from "@/shared/lib/handle-api-error";
import { useAddTunnelHostname, useUpdateTunnelHostname } from "../hooks/use-tunnel-hostnames";
import type { TunnelPublicHostname } from "../model/schema";

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
  const isEditing = hostname !== null;
  const addHostname = useAddTunnelHostname(environmentId, tunnelId);
  const updateHostname = useUpdateTunnelHostname(environmentId, tunnelId);
  const [hostnameValue, setHostnameValue] = useState(hostname?.hostname ?? "");
  const [service, setService] = useState(hostname?.service ?? "");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const isSaving = addHostname.isPending || updateHostname.isPending;

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    setErrorMessage(null);
    const callbacks = {
      onSuccess: () => onClose(),
      onError: (err: unknown) => setErrorMessage(getErrorMessage(err)),
    };
    if (isEditing && hostname) {
      updateHostname.mutate({ hostnameId: hostname.id, service }, callbacks);
    } else {
      addHostname.mutate({ hostname: hostnameValue, service }, callbacks);
    }
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

        <div className="space-y-1.5">
          <Label htmlFor="hostname-value">{t("hostnames.hostnameLabel")}</Label>
          <Input
            id="hostname-value"
            value={hostnameValue}
            onChange={(event) => setHostnameValue(event.target.value)}
            disabled={isEditing}
            required
            autoFocus={!isEditing}
          />
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
          <Button type="submit" disabled={isSaving}>
            {isSaving ? t("hostnames.saving") : t("hostnames.save")}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
