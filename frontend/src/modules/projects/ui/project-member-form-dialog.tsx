"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@/shared/ui/button";
import { Label } from "@/shared/ui/label";
import { Dialog, DialogErrorAlert } from "@/shared/ui/dialog";
import { useApiErrorMessage } from "@/shared/lib/handle-api-error";
import { useUsers } from "@/entities/user";
import { fetchProjectRoles } from "../api/fetchers";
import { projectRolesKeys } from "../api/query-keys";
import { useAddProjectMember } from "../hooks/use-add-project-member";
import { useAssignMemberProjectRole } from "../hooks/use-assign-member-project-role";
import { Users } from "lucide-react";

/**
 * fetchProjectRoles is already scoped to `projectId`, so a role belonging
 * to a different project can structurally never appear in this picker.
 */
function ProjectRolePicker({
  projectId,
  projectRoleId,
  onChange,
}: {
  projectId: string;
  projectRoleId: string;
  onChange: (value: string) => void;
}) {
  const t = useTranslations("projects");
  const { data: roles = [] } = useQuery({
    queryKey: projectRolesKeys.forProject(projectId),
    queryFn: () => fetchProjectRoles(projectId),
  });

  return (
    <select
      id="project-member-role"
      value={projectRoleId}
      onChange={(e) => onChange(e.target.value)}
      className="h-10 w-full rounded-md border bg-background px-3 text-sm"
    >
      <option value="">{t("form.noProjectRole")}</option>
      {roles.map((role) => (
        <option key={role.id} value={role.id}>
          {role.name}
        </option>
      ))}
    </select>
  );
}

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
  const assignRole = useAssignMemberProjectRole(projectId);

  const [userId, setUserId] = useState("");
  const [projectRoleId, setProjectRoleId] = useState("");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  if (!isOpen) return null;

  const isPending = addMember.isPending || assignRole.isPending;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);
    addMember.mutate(userId, {
      onSuccess: () => {
        if (!projectRoleId) {
          onClose();
          return;
        }
        assignRole.mutate(
          { userId, projectRoleId },
          {
            onSuccess: () => onClose(),
            onError: (err) => setErrorMessage(getErrorMessage(err)),
          },
        );
      },
      onError: (err) => setErrorMessage(getErrorMessage(err)),
    });
  };

  return (
    <Dialog
      icon={Users}
      title={t("form.addMemberTitle")}
      onClose={onClose}
      closeLabel={t("form.cancel")}
      disableClose={isPending}
    >
      <form onSubmit={handleSubmit} className="flex flex-col gap-4 overflow-y-auto p-6">
        {errorMessage && <DialogErrorAlert message={errorMessage} />}

        <div className="space-y-2">
          <Label htmlFor="project-member-user">{t("form.selectUserLabel")}</Label>
          <UserPicker userId={userId} onChange={setUserId} excludeUserIds={excludeUserIds} />
        </div>

        <div className="space-y-2">
          <Label htmlFor="project-member-role">{t("form.projectRoleLabel")}</Label>
          <ProjectRolePicker projectId={projectId} projectRoleId={projectRoleId} onChange={setProjectRoleId} />
        </div>

        <div className="mt-2 flex items-center justify-end gap-3">
          <Button type="button" variant="outline" onClick={onClose} disabled={isPending}>
            {t("form.cancel")}
          </Button>
          <Button type="submit" disabled={isPending || !userId}>
            {isPending ? t("form.saving") : t("actions.addMember")}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
