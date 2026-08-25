"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/input";
import { Label } from "@/shared/ui/label";
import { Dialog, DialogErrorAlert } from "@/shared/ui/dialog";
import { useApiErrorMessage } from "@/shared/lib/handle-api-error";
import { useCreateTunnel } from "../hooks/use-tunnels";
import { IconCloudflare } from "@/shared/ui/icons";

export function CreateTunnelDialog({ environmentId, onClose }: { environmentId: string; onClose: () => void }) {
  const t = useTranslations("cloudflareTunnels");
  const getErrorMessage = useApiErrorMessage("cloudflareTunnels");
  const createTunnel = useCreateTunnel(environmentId);
  const [name, setName] = useState("");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [createdToken, setCreatedToken] = useState<string | null>(null);

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    setErrorMessage(null);
    createTunnel.mutate(name, {
      onSuccess: (result) => setCreatedToken(result.token),
      onError: (err: unknown) => setErrorMessage(getErrorMessage(err)),
    });
  };

  return (
    <Dialog
      icon={IconCloudflare}
      title={t("createDialog.title")}
      onClose={onClose}
      closeLabel={t("createDialog.cancel")}
    >
      <div className="overflow-y-auto p-6">
        {createdToken ? (
          <div className="flex flex-col gap-3">
            <p className="text-sm font-semibold text-amber-700 dark:text-amber-300">
              {t("tokenRevealed.title")}
            </p>
            <code className="break-all rounded bg-muted px-2 py-1.5 font-mono text-xs">{createdToken}</code>
            <p className="text-xs text-muted-foreground">{t("tokenRevealed.hint")}</p>
            <div className="flex justify-end pt-2">
              <Button onClick={onClose}>{t("createDialog.done")}</Button>
            </div>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            {errorMessage && <DialogErrorAlert message={errorMessage} />}

            <div className="space-y-1.5">
              <Label htmlFor="tunnel-name">{t("createDialog.nameLabel")}</Label>
              <Input
                id="tunnel-name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                required
                autoFocus
              />
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <Button type="button" variant="outline" onClick={onClose}>
                {t("createDialog.cancel")}
              </Button>
              <Button type="submit" disabled={createTunnel.isPending || name.trim().length === 0}>
                {createTunnel.isPending ? t("createDialog.creating") : t("createDialog.create")}
              </Button>
            </div>
          </form>
        )}
      </div>
    </Dialog>
  );
}
