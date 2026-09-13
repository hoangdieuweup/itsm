"use client";

import { useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { Check } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/input";
import { Label } from "@/shared/ui/label";
import { Dialog, DialogErrorAlert } from "@/shared/ui/dialog";
import { useApiErrorMessage } from "@/shared/lib/handle-api-error";
import { IconPermission } from "@/shared/ui/icons";
import {
  fetchAssignablePermissions,
  type ProjectRole,
  type ProjectRolePermissionItem,
} from "../api/fetchers";
import { assignablePermissionsKeys } from "../api/query-keys";
import { useCreateProjectRole } from "../hooks/use-create-project-role";
import { useUpdateProjectRole } from "../hooks/use-update-project-role";

interface ProjectRoleFormDialogProps {
  isOpen: boolean;
  onClose: () => void;
  projectId: string;
  role?: ProjectRole | null;
}

export function ProjectRoleFormDialog({ isOpen, onClose, projectId, role }: ProjectRoleFormDialogProps) {
  if (!isOpen) return null;

  return (
    <ProjectRoleFormInner
      key={role ? `edit-${role.id}` : "create-new"}
      projectId={projectId}
      role={role}
      onClose={onClose}
    />
  );
}

function ProjectRoleFormInner({
  projectId,
  role,
  onClose,
}: {
  projectId: string;
  role?: ProjectRole | null;
  onClose: () => void;
}) {
  const t = useTranslations("projects");
  const tRoles = useTranslations("roles");
  const getErrorMessage = useApiErrorMessage("projects");
  const { data: assignablePermissions = [], isPending: permissionsLoading } = useQuery({
    queryKey: assignablePermissionsKeys.all,
    queryFn: fetchAssignablePermissions,
  });
  const createRole = useCreateProjectRole(projectId);
  const updateRole = useUpdateProjectRole(projectId);

  const isEditing = Boolean(role);
  const [name, setName] = useState(() => role?.name ?? "");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(
    () => new Set(role?.permissions.map((p) => p.id) ?? []),
  );
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const groupedPermissions = useMemo(() => {
    const groups: Record<string, ProjectRolePermissionItem[]> = {};
    for (const perm of assignablePermissions) {
      const list = groups[perm.resource] ?? [];
      list.push(perm);
      groups[perm.resource] = list;
    }
    return groups;
  }, [assignablePermissions]);

  const assignableIds = useMemo(
    () => new Set(assignablePermissions.map((perm) => perm.id)),
    [assignablePermissions],
  );

  const togglePermission = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const isPending = createRole.isPending || updateRole.isPending || permissionsLoading;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);
    const permissionIds = Array.from(selectedIds).filter((id) => assignableIds.has(id));
    const callbacks = {
      onSuccess: () => onClose(),
      onError: (err: unknown) => setErrorMessage(getErrorMessage(err)),
    };

    if (isEditing && role) {
      updateRole.mutate({ id: role.id, data: { name, permissionIds } }, callbacks);
    } else {
      createRole.mutate({ name, permissionIds }, callbacks);
    }
  };

  return (
    <Dialog
      icon={IconPermission}
      title={isEditing ? t("editProjectRole") : t("createProjectRole")}
      onClose={onClose}
      closeLabel={t("form.cancel")}
      size="xl"
      disableClose={isPending}
    >
      <form onSubmit={handleSubmit} className="flex flex-1 min-h-0 flex-col overflow-hidden h-[min(560px,70vh)]">
        <div className="flex-1 min-h-0 space-y-6 overflow-y-auto px-7 sm:px-8 py-5">
          {errorMessage && <DialogErrorAlert message={errorMessage} />}

          <div className="space-y-2">
            <Label htmlFor="project-role-name">{t("form.nameLabel")}</Label>
            <Input
              id="project-role-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
              className="h-10"
            />
          </div>

          <div className="space-y-4">
            <Label className="text-sm font-bold text-foreground">{t("form.permissionsLabel")}</Label>
            <div className="space-y-6">
              {Object.entries(groupedPermissions).map(([resource, perms]) => (
                <div key={resource} className="space-y-2.5">
                  <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                    {tRoles.has(`resources.${resource}` as Parameters<typeof tRoles>[0])
                      ? tRoles(`resources.${resource}` as Parameters<typeof tRoles>[0])
                      : resource}
                  </span>
                  <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
                    {perms.map((perm) => {
                      const isChecked = selectedIds.has(perm.id);
                      const catalogKey = `catalog.${perm.descriptionKey}` as Parameters<typeof tRoles>[0];
                      const label = tRoles.has(catalogKey) ? tRoles(catalogKey) : perm.action;
                      return (
                        <button
                          key={perm.id}
                          type="button"
                          role="checkbox"
                          aria-checked={isChecked}
                          onClick={() => togglePermission(perm.id)}
                          className={`flex w-full cursor-pointer text-left items-center gap-3 rounded-2xl border p-3.5 text-xs transition-all select-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/40 ${
                            isChecked
                              ? "border-blue-500/40 bg-blue-500/10 text-foreground font-medium dark:border-blue-500/30 dark:bg-blue-500/15 shadow-2xs"
                              : "border-border/40 bg-card/60 text-muted-foreground hover:border-border/70 hover:bg-muted/40 hover:text-foreground"
                          }`}
                        >
                          <div
                            className={`flex size-5 shrink-0 items-center justify-center rounded-lg border transition-colors ${
                              isChecked
                                ? "border-blue-600 bg-blue-600 text-white dark:border-blue-500 dark:bg-blue-500 shadow-2xs"
                                : "border-muted-foreground/30 bg-background"
                            }`}
                          >
                            {isChecked && <Check className="size-3 stroke-[3]" />}
                          </div>
                          <div className="flex flex-col overflow-hidden">
                            <span className="text-xs font-bold text-foreground leading-tight">{label}</span>
                            <span className="font-mono text-[10px] text-muted-foreground leading-tight mt-0.5">
                              {perm.resource}:{perm.action}
                            </span>
                          </div>
                        </button>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>

        <div className="flex shrink-0 items-center justify-end gap-3 border-t border-border/30 bg-card/80 px-7 sm:px-8 py-4 backdrop-blur-md">
          <Button type="button" variant="outline" onClick={onClose} disabled={isPending}>
            {t("form.cancel")}
          </Button>
          <Button type="submit" disabled={isPending || !name.trim()}>
            {isPending ? t("form.saving") : isEditing ? t("form.save") : t("form.create")}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
