"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { X } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/input";
import { Label } from "@/shared/ui/label";
import { useApiErrorMessage } from "@/shared/lib/handle-api-error";
import { useCreateTunnel } from "../hooks/use-tunnels";

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
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 animate-in fade-in-0"
      role="dialog"
      aria-modal="true"
      aria-labelledby="create-tunnel-title"
    >
      <div className="w-full max-w-md rounded-lg border border-border bg-background p-6 shadow-lg animate-in zoom-in-95">
        <div className="mb-4 flex items-center justify-between">
          <h2 id="create-tunnel-title" className="text-lg font-semibold">
            {t("createDialog.title")}
          </h2>
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={onClose}
            aria-label={t("createDialog.cancel")}
            className="focus-visible:ring-2 focus-visible:ring-primary"
          >
            <X className="size-4" aria-hidden="true" />
          </Button>
        </div>

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
            {errorMessage && (
              <div role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
                {errorMessage}
              </div>
            )}

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
    </div>
  );
}
