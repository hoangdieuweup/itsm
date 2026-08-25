"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { Plus, Pencil, Trash2, ShieldCheck } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { ConfirmDialog } from "@/shared/ui/confirm-dialog";
import { CanInProject } from "@/entities/permission";
import { ACTIONS, RESOURCES } from "@/shared/constants/permissions";
import { fetchProjectRoles, type ProjectRole } from "../api/fetchers";
import { projectRolesKeys } from "../api/query-keys";
import { useDeleteProjectRole } from "../hooks/use-delete-project-role";
import { ProjectRoleFormDialog } from "./project-role-form-dialog";

export function ProjectRolesSection({ projectId }: { projectId: string }) {
  const t = useTranslations("projects");
  const { data: roles = [] } = useQuery({
    queryKey: projectRolesKeys.forProject(projectId),
    queryFn: () => fetchProjectRoles(projectId),
  });
  const deleteRole = useDeleteProjectRole(projectId);
  const [formTarget, setFormTarget] = useState<ProjectRole | "create" | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<ProjectRole | null>(null);

  return (
    <section className="flex flex-col gap-3 rounded-xl border bg-card p-5">
      <div className="flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-sm font-bold uppercase tracking-wider text-muted-foreground">
          <ShieldCheck className="size-4" /> {t("sections.projectRoles")} ({roles.length})
        </h2>
        <CanInProject I={ACTIONS.MANAGE} a={RESOURCES.PROJECT_ROLE}>
          <Button size="sm" variant="outline" onClick={() => setFormTarget("create")} className="gap-1.5 shadow-2xs">
            <Plus className="size-3.5" /> {t("actions.addProjectRole")}
          </Button>
        </CanInProject>
      </div>
      <div className="flex flex-col divide-y">
        {roles.length === 0 && <p className="text-sm text-muted-foreground">{t("empty.projectRoles")}</p>}
        {roles.map((role) => (
          <div key={role.id} className="flex items-center justify-between py-2 text-sm">
            <div className="flex flex-col overflow-hidden">
              <span className="font-medium text-foreground truncate">{role.name}</span>
              <span className="text-xs text-muted-foreground">
                {t("projectRolePermissionCount", { count: role.permissions.length })}
              </span>
            </div>
            <CanInProject I={ACTIONS.MANAGE} a={RESOURCES.PROJECT_ROLE}>
              <div className="flex shrink-0 gap-2">
                <button
                  type="button"
                  onClick={() => setFormTarget(role)}
                  className="flex size-7 items-center justify-center rounded-lg text-muted-foreground hover:bg-muted hover:text-foreground cursor-pointer"
                  title={t("actions.edit")}
                >
                  <Pencil className="size-3.5" />
                </button>
                <button
                  type="button"
                  onClick={() => setDeleteTarget(role)}
                  className="flex size-7 items-center justify-center rounded-lg text-rose-600 hover:bg-rose-500/10 hover:text-rose-700 dark:hover:bg-rose-950/50 cursor-pointer"
                  title={t("actions.delete")}
                >
                  <Trash2 className="size-3.5" />
                </button>
              </div>
            </CanInProject>
          </div>
        ))}
      </div>

      {formTarget !== null && (
        <ProjectRoleFormDialog
          isOpen
          onClose={() => setFormTarget(null)}
          projectId={projectId}
          role={formTarget === "create" ? null : formTarget}
        />
      )}
      <ConfirmDialog
        isOpen={deleteTarget !== null}
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => {
          if (deleteTarget) deleteRole.mutate(deleteTarget.id, { onSuccess: () => setDeleteTarget(null) });
        }}
        title={t("deleteConfirm.projectRoleTitle")}
        description={t("deleteConfirm.projectRoleDescription", { name: deleteTarget?.name ?? "" })}
        isLoading={deleteRole.isPending}
      />
    </section>
  );
}
