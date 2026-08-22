"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { X, UserPlus } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { Label } from "@/shared/ui/label";
import { apiFetch } from "@/shared/lib/api-client";
import { API_CONFIG } from "@/shared/constants/api";
import { useApiErrorMessage } from "@/shared/lib/handle-api-error";
import { useAssignCloudflareAccountManager } from "../hooks/use-assign-cloudflare-account-manager";
import type { AccessLevel } from "../api/fetchers";

interface CloudflareAccountManagerFormDialogProps {
  accountId: string;
  onClose: () => void;
}

interface UserOption {
  id: string;
  email: string;
  name: string;
}

export function CloudflareAccountManagerFormDialog({
  accountId,
  onClose,
}: CloudflareAccountManagerFormDialogProps) {
  const t = useTranslations("cloudflareAccounts");
  const [userId, setUserId] = useState("");
  const [accessLevel, setAccessLevel] = useState<AccessLevel>("viewer");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const getErrorMessage = useApiErrorMessage("cloudflareAccounts");

  // Reuses the existing GET /users list — no dedicated user-picker component
  // exists in shared/ui yet, so this is a small inline query rather than a
  // new shared primitive (out of scope to build one for this phase).
  const { data: users } = useQuery({
    queryKey: ["users", "picker"],
    queryFn: () => apiFetch<{ items: UserOption[] }>(`${API_CONFIG.ENDPOINTS.USERS.ROOT}?limit=100`),
  });

  const assign = useAssignCloudflareAccountManager(accountId);

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    setErrorMessage(null);
    assign.mutate(
      { userId, accessLevel },
      { onSuccess: () => onClose(), onError: (err) => setErrorMessage(getErrorMessage(err)) },
    );
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 animate-in fade-in-0"
      role="dialog"
      aria-modal="true"
      aria-labelledby="cloudflare-manager-form-title"
    >
      <div className="w-full max-w-md rounded-lg border border-border bg-background p-6 shadow-lg animate-in zoom-in-95">
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            <div className="flex size-8 items-center justify-center rounded-md bg-primary/10">
              <UserPlus className="size-4 text-primary" aria-hidden="true" />
            </div>
            <h2 id="cloudflare-manager-form-title" className="text-lg font-semibold">
              {t("managers.assign")}
            </h2>
          </div>
          <Button variant="ghost" size="icon-sm" onClick={onClose} aria-label={t("form.cancel")}>
            <X className="size-4" aria-hidden="true" />
          </Button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {errorMessage && (
            <div role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {errorMessage}
            </div>
          )}

          <div className="space-y-1.5">
            <Label htmlFor="userId">{t("managers.user")}</Label>
            <select
              id="userId"
              value={userId}
              onChange={(e) => setUserId(e.target.value)}
              required
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
            >
              <option value="" disabled>
                —
              </option>
              {users?.items.map((user) => (
                <option key={user.id} value={user.id}>
                  {user.name} ({user.email})
                </option>
              ))}
            </select>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="accessLevel">{t("managers.accessLevel")}</Label>
            <select
              id="accessLevel"
              value={accessLevel}
              onChange={(e) => setAccessLevel(e.target.value as AccessLevel)}
              className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ring"
            >
              <option value="viewer">{t("managers.levels.viewer")}</option>
              <option value="editor">{t("managers.levels.editor")}</option>
              <option value="owner">{t("managers.levels.owner")}</option>
            </select>
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="outline" onClick={onClose}>
              {t("form.cancel")}
            </Button>
            <Button type="submit" disabled={assign.isPending}>
              {assign.isPending ? t("form.saving") : t("form.save")}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
