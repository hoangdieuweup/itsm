"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@/shared/ui/button";
import { Label } from "@/shared/ui/label";
import { Dialog, DialogErrorAlert } from "@/shared/ui/dialog";
import { PAGINATION } from "@/shared/constants/pagination";
import { fetchUsers } from "@/entities/user";
import { useApiErrorMessage } from "@/shared/lib/handle-api-error";
import { useAssignCloudflareAccountManager } from "../hooks/use-assign-cloudflare-account-manager";
import { ACCESS_LEVEL, type AccessLevel } from "@/shared/constants/cloudflare";
import { IconUsers } from "@/shared/ui/icons";

interface CloudflareAccountManagerFormDialogProps {
  accountId: string;
  onClose: () => void;
}

/**
 * Local key for this module's own user-picker query — deliberately not
 * `usersKeys` from `@/entities/user`: this picker's filters/shape aren't
 * the same cache concern as the Users admin page's own list.
 */
const userPickerKeys = {
  all: ["cloudflare-accounts", "user-picker"] as const,
  list: (limit: number) => [...userPickerKeys.all, limit] as const,
};

export function CloudflareAccountManagerFormDialog({
  accountId,
  onClose,
}: CloudflareAccountManagerFormDialogProps) {
  const t = useTranslations("cloudflareAccounts");
  const [userId, setUserId] = useState("");
  const [accessLevel, setAccessLevel] = useState<AccessLevel>(ACCESS_LEVEL.VIEWER);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const getErrorMessage = useApiErrorMessage("cloudflareAccounts");

  // Reuses GET /users through the user entity's fetcher — no dedicated
  // user-picker component exists in shared/ui yet. Lists at most one full
  // page (PAGINATION.MAX_PAGE_SIZE users).
  const { data: users } = useQuery({
    queryKey: userPickerKeys.list(PAGINATION.MAX_PAGE_SIZE),
    queryFn: () => fetchUsers(PAGINATION.MAX_PAGE_SIZE, 0),
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
    <Dialog icon={IconUsers} title={t("managers.assign")} onClose={onClose} closeLabel={t("form.cancel")}>
      <form onSubmit={handleSubmit} className="space-y-4 overflow-y-auto p-6">
        {errorMessage && <DialogErrorAlert message={errorMessage} />}

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
            {Object.values(ACCESS_LEVEL).map((level) => (
              <option key={level} value={level}>
                {t(`managers.levels.${level}`)}
              </option>
            ))}
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
    </Dialog>
  );
}
