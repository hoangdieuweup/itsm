"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Eye, EyeOff } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/input";
import { Label } from "@/shared/ui/label";
import { Dialog, DialogErrorAlert } from "@/shared/ui/dialog";
import { useApiErrorMessage } from "@/shared/lib/handle-api-error";
import type { CloudflareAccount } from "@/entities/cloudflare-account";
import { useCreateCloudflareAccount } from "../hooks/use-create-cloudflare-account";
import { useUpdateCloudflareAccount } from "../hooks/use-update-cloudflare-account";
import { IconCloudflare } from "@/shared/ui/icons";

interface CloudflareAccountFormDialogProps {
  account: CloudflareAccount | null;
  onClose: () => void;
}

export function CloudflareAccountFormDialog({ account, onClose }: CloudflareAccountFormDialogProps) {
  const t = useTranslations("cloudflareAccounts");
  const isEditing = Boolean(account);
  const [label, setLabel] = useState(account?.label ?? "");
  const [cfAccountId, setCfAccountId] = useState(account?.cfAccountId ?? "");
  const [apiToken, setApiToken] = useState("");
  const [tokenVisible, setTokenVisible] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const getErrorMessage = useApiErrorMessage("cloudflareAccounts");

  const create = useCreateCloudflareAccount();
  const update = useUpdateCloudflareAccount();
  const isSaving = create.isPending || update.isPending;

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    setErrorMessage(null);
    const callbacks = {
      onSuccess: () => onClose(),
      onError: (err: unknown) => setErrorMessage(getErrorMessage(err)),
    };
    if (isEditing && account) {
      update.mutate({ id: account.id, data: { label, apiToken: apiToken || undefined } }, callbacks);
    } else {
      create.mutate({ label, cfAccountId, apiToken }, callbacks);
    }
  };

  return (
    <Dialog
      icon={IconCloudflare}
      title={isEditing ? t("form.editTitle") : t("form.createTitle")}
      onClose={onClose}
      closeLabel={t("form.cancel")}
    >
      <form onSubmit={handleSubmit} className="space-y-4 overflow-y-auto p-6">
        {errorMessage && <DialogErrorAlert message={errorMessage} />}

        <div className="space-y-1.5">
          <Label htmlFor="label">{t("form.label")}</Label>
          <Input id="label" value={label} onChange={(e) => setLabel(e.target.value)} required />
        </div>

        {!isEditing && (
          <div className="space-y-1.5">
            <Label htmlFor="cfAccountId">{t("form.cfAccountId")}</Label>
            <Input
              id="cfAccountId"
              value={cfAccountId}
              onChange={(e) => setCfAccountId(e.target.value)}
              required
            />
          </div>
        )}

        <div className="space-y-1.5">
          <Label htmlFor="apiToken">{isEditing ? t("form.rotateToken") : t("form.apiToken")}</Label>
          <div className="relative">
            <Input
              id="apiToken"
              type={tokenVisible ? "text" : "password"}
              value={apiToken}
              onChange={(e) => setApiToken(e.target.value)}
              required={!isEditing}
              className="pr-10"
              aria-describedby="apiToken-hint"
            />
            <Button
              type="button"
              variant="ghost"
              size="icon-xs"
              className="absolute right-1 top-1/2 -translate-y-1/2"
              onClick={() => setTokenVisible((visible) => !visible)}
              aria-label={tokenVisible ? t("actions.hideToken") : t("actions.revealToken")}
              aria-pressed={tokenVisible}
            >
              {tokenVisible ? (
                <EyeOff className="size-4" aria-hidden="true" />
              ) : (
                <Eye className="size-4" aria-hidden="true" />
              )}
            </Button>
          </div>
          <p id="apiToken-hint" className="text-xs text-muted-foreground">
            {t("form.apiTokenHint")}
          </p>
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="outline" onClick={onClose}>
            {t("form.cancel")}
          </Button>
          <Button type="submit" disabled={isSaving}>
            {isSaving ? t("form.saving") : isEditing ? t("form.save") : t("form.create")}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
