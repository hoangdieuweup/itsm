"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Button } from "@/shared/ui/button";
import { Label } from "@/shared/ui/label";
import { Dialog, DialogErrorAlert } from "@/shared/ui/dialog";
import { useApiErrorMessage } from "@/shared/lib/handle-api-error";
import { useUsers } from "@/entities/user";
import { useAddProjectMember } from "../hooks/use-add-project-member";
import { Users } from "lucide-react";

/**
 * useUsers is a Suspense query with no built-in "disabled" mode — this is
 * only ever mounted while the dialog is open, mirroring how
 * CreateManualIncidentDialog's EnvironmentPicker gates its own Suspense query.
 */
function UserPicker({
  userId,
  onChange,
  excludeUserIds,
}: {
  userId: string;
  onChange: (value: string) => void;
  excludeUserIds: Set<string>;
}) {
  const t = useTranslations("projects");
  const { data: usersPage } = useUsers(100, 0);
  const options = usersPage.items.filter((user) => !excludeUserIds.has(user.id));

  return (
    <select
      id="project-member-user"
      value={userId}
      onChange={(e) => onChange(e.target.value)}
      required
      className="h-10 w-full rounded-md border bg-background px-3 text-sm"
    >
      <option value="" disabled>
        {t("form.selectUser")}
      </option>
      {options.map((user) => (
        <option key={user.id} value={user.id}>
          {user.name} ({user.email})
        </option>
      ))}
    </select>
  );
}

interface ProjectMemberFormDialogProps {
  isOpen: boolean;
  onClose: () => void;
  projectId: string;
  excludeUserIds: Set<string>;
}

export function ProjectMemberFormDialog({
  isOpen,
  onClose,
  projectId,
  excludeUserIds,
}: ProjectMemberFormDialogProps) {
  const t = useTranslations("projects");
  const getErrorMessage = useApiErrorMessage("projects");
  const addMember = useAddProjectMember(projectId);

  const [userId, setUserId] = useState("");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);
    addMember.mutate(userId, {
      onSuccess: () => onClose(),
      onError: (err) => setErrorMessage(getErrorMessage(err)),
    });
  };

  return (
    <Dialog
      icon={Users}
      title={t("form.addMemberTitle")}
      onClose={onClose}
      closeLabel={t("form.cancel")}
      disableClose={addMember.isPending}
    >
      <form onSubmit={handleSubmit} className="flex flex-col gap-4 overflow-y-auto p-6">
        {errorMessage && <DialogErrorAlert message={errorMessage} />}

        <div className="space-y-2">
          <Label htmlFor="project-member-user">{t("form.selectUserLabel")}</Label>
          <UserPicker userId={userId} onChange={setUserId} excludeUserIds={excludeUserIds} />
        </div>

        <div className="mt-2 flex items-center justify-end gap-3">
          <Button type="button" variant="outline" onClick={onClose} disabled={addMember.isPending}>
            {t("form.cancel")}
          </Button>
          <Button type="submit" disabled={addMember.isPending || !userId}>
            {addMember.isPending ? t("form.saving") : t("actions.addMember")}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
