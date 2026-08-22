"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { FolderKanban, Plus, Pencil, Trash2 } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { ConfirmDialog } from "@/shared/ui/confirm-dialog";
import { Can } from "@/entities/permission";
import { useProjectsQuery, type Project } from "@/entities/project";
import { Link } from "@/shared/lib/i18n/navigation";
import { ROUTES } from "@/shared/constants/routes";
import { ACTIONS, RESOURCES } from "@/shared/constants/permissions";
import { useDeleteProject } from "../hooks/use-delete-project";
import { ProjectFormDialog } from "./project-form-dialog";

export function ProjectsPageContent() {
  const t = useTranslations("projects");
  const { data } = useProjectsQuery(50, 0);
  const deleteProject = useDeleteProject();

  const [formTarget, setFormTarget] = useState<Project | "create" | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Project | null>(null);

  return (
    <div className="flex flex-1 flex-col gap-6">
      <div className="flex items-center justify-between">
        <div className="flex flex-col gap-1">
          <h1 className="text-xl font-bold text-foreground">{t("title")}</h1>
          <p className="text-sm text-muted-foreground">{t("description")}</p>
        </div>
        <Can I={ACTIONS.CREATE} a={RESOURCES.PROJECT}>
          <Button onClick={() => setFormTarget("create")}>
            <Plus className="mr-2 size-4" />
            {t("actions.create")}
          </Button>
        </Can>
      </div>

      {data.items.length === 0 ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-3 rounded-xl border bg-card py-16 text-center">
          <div className="flex size-12 items-center justify-center rounded-xl bg-muted text-muted-foreground">
            <FolderKanban className="size-6" aria-hidden />
          </div>
          <h2 className="text-lg font-semibold text-foreground">{t("empty.title")}</h2>
          <p className="max-w-sm text-sm text-muted-foreground">{t("empty.description")}</p>
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border bg-card">
          <table className="w-full text-sm">
            <thead className="border-b bg-muted/40 text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              <tr>
                <th className="px-4 py-3">{t("table.name")}</th>
                <th className="px-4 py-3">{t("table.description")}</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody className="divide-y">
              {data.items.map((project) => (
                <tr key={project.id} className="hover:bg-muted/30">
                  <td className="px-4 py-3 font-medium text-foreground">
                    <Link
                      href={`${ROUTES.adminProjects}/${project.id}`}
                      className="hover:underline"
                    >
                      {project.name}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">
                    {project.description ?? "—"}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex justify-end gap-2">
                      <Can I={ACTIONS.UPDATE} a={RESOURCES.PROJECT}>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setFormTarget(project)}
                        >
                          <Pencil className="size-3.5" />
                        </Button>
                      </Can>
                      <Can I={ACTIONS.DELETE} a={RESOURCES.PROJECT}>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => setDeleteTarget(project)}
                        >
                          <Trash2 className="size-3.5" />
                        </Button>
                      </Can>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {formTarget !== null && (
        <ProjectFormDialog
          isOpen
          onClose={() => setFormTarget(null)}
          project={formTarget === "create" ? null : formTarget}
        />
      )}

      <ConfirmDialog
        isOpen={deleteTarget !== null}
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => {
          if (deleteTarget) {
            deleteProject.mutate(deleteTarget.id, { onSuccess: () => setDeleteTarget(null) });
          }
        }}
        title={t("deleteConfirm.title")}
        description={t("deleteConfirm.description", { name: deleteTarget?.name ?? "" })}
        isLoading={deleteProject.isPending}
      />
    </div>
  );
}
