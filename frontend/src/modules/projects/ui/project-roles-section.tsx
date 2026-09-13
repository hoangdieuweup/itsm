"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { Plus, Pencil, Trash2, ShieldCheck } from "lucide-react";
import { ConfirmDialog } from "@/shared/ui/confirm-dialog";
import { Skeleton } from "@/shared/ui/skeleton";
import { CanInProject } from "@/entities/permission";
import { ACTIONS, RESOURCES } from "@/shared/constants/permissions";
import { fetchProjectRoles } from "../api/fetchers";
import type { ProjectRole } from "../model/schema";
import { projectRolesKeys } from "../api/query-keys";
import { useDeleteProjectRole } from "../hooks/use-delete-project-role";
import { ProjectRoleFormDialog } from "./project-role-form-dialog";

export function ProjectRolesSection({ projectId }: { projectId: string }) {
  const t = useTranslations("projects");
  const { data: roles = [], isLoading } = useQuery({
    queryKey: projectRolesKeys.forProject(projectId),
    queryFn: () => fetchProjectRoles(projectId),
  });
  const deleteRole = useDeleteProjectRole(projectId);
  const [formTarget, setFormTarget] = useState<ProjectRole | "create" | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<ProjectRole | null>(null);

  return (
    <>
      <div className="rounded-2xl border border-border/50 bg-card/80 backdrop-blur-xl shadow-sm overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border/30 px-5 py-3.5">
          <div className="flex items-center gap-2">
            <ShieldCheck className="size-4 text-primary" />
            <h2 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
              {t("sections.projectRoles")} ({roles.length})
            </h2>
          </div>
          <CanInProject I={ACTIONS.MANAGE} a={RESOURCES.PROJECT_ROLE}>
            <button
              type="button"
              onClick={() => setFormTarget("create")}
              className="flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs font-semibold text-primary hover:bg-primary/10 transition-colors cursor-pointer"
            >
              <Plus className="size-3" /> {t("actions.addProjectRole")}
            </button>
          </CanInProject>
        </div>

        {/* Roles List */}
        <div className="divide-y divide-border/20">
          {isLoading ? (
            <div className="space-y-2 p-3">
              <Skeleton className="h-10 w-full rounded-xl" />
              <Skeleton className="h-10 w-full rounded-xl" />
            </div>
          ) : roles.length === 0 ? (
            <div className="flex items-center justify-center py-10 px-5">
              <p className="text-xs text-muted-foreground">{t("empty.projectRoles")}</p>
            </div>
          ) : (
            roles.map((role) => (
              <div
                key={role.id}
                className="flex items-center justify-between px-5 py-3 transition-colors hover:bg-muted/30"
              >
                <div className="flex flex-col min-w-0">
                  <span className="text-sm font-semibold text-foreground truncate leading-tight">
                    {role.name}
                  </span>
                  <span className="text-[11px] text-muted-foreground leading-tight">
                    {t("projectRolePermissionCount", { count: role.permissions.length })}
                  </span>
                </div>
                <CanInProject I={ACTIONS.MANAGE} a={RESOURCES.PROJECT_ROLE}>
                  <div className="flex shrink-0 items-center gap-1">
                    <button
                      type="button"
                      onClick={() => setFormTarget(role)}
                      className="flex size-6 items-center justify-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground cursor-pointer transition-colors"
                      title={t("actions.edit")}
                    >
                      <Pencil className="size-3" />
                    </button>
                    <button
                      type="button"
                      onClick={() => setDeleteTarget(role)}
                      className="flex size-6 items-center justify-center rounded-md text-rose-500/70 hover:bg-rose-500/10 hover:text-rose-600 cursor-pointer transition-colors"
                      title={t("actions.delete")}
                    >
                      <Trash2 className="size-3" />
                    </button>
                  </div>
                </CanInProject>
              </div>
            ))
          )}
        </div>
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
    </>
  );
}
