"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { FolderKanban, Plus, Pencil, Trash2, ArrowRight, Layers, Sparkles } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { ConfirmDialog } from "@/shared/ui/confirm-dialog";
import { Can } from "@/entities/permission";
import { useProjectsQuery, type Project } from "@/entities/project";
import { Link } from "@/shared/lib/i18n/navigation";
import { ROUTES } from "@/shared/constants/routes";
import { ACTIONS, RESOURCES } from "@/shared/constants/permissions";
import { useDeleteProject } from "../hooks/use-delete-project";
import { ProjectFormDialog } from "./project-form-dialog";
import { m, type Variants } from "@/shared/lib/motion";

const containerVariants: Variants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.07,
    },
  },
};

const itemVariants: Variants = {
  hidden: { opacity: 0, y: 16 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.35 },
  },
};

export function ProjectsPageContent() {
  const t = useTranslations("projects");
  const { data } = useProjectsQuery(50, 0);
  const deleteProject = useDeleteProject();

  const [formTarget, setFormTarget] = useState<Project | "create" | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Project | null>(null);

  return (
    <m.div
      variants={containerVariants}
      initial="hidden"
      animate="visible"
      className="flex flex-1 flex-col gap-6"
    >
      {/* Header Section */}
      <m.div variants={itemVariants} className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-2xl font-extrabold tracking-tight text-foreground sm:text-3xl">
              {t("title")}
            </h1>
            <span className="inline-flex items-center rounded-full border border-emerald-500/30 bg-emerald-500/15 px-2.5 py-0.5 font-mono text-xs font-bold text-emerald-600 dark:text-emerald-400">
              {data.total}
            </span>
          </div>
          <p className="mt-1 text-sm text-muted-foreground">{t("description")}</p>
        </div>

        <Can I={ACTIONS.CREATE} a={RESOURCES.PROJECT}>
          <Button
            onClick={() => setFormTarget("create")}
            className="gap-2 self-start bg-gradient-to-r from-emerald-600 to-teal-600 font-semibold text-white shadow-md shadow-emerald-500/25 hover:from-emerald-700 hover:to-teal-700 sm:self-auto"
          >
            <Plus className="size-4" />
            {t("actions.create")}
          </Button>
        </Can>
      </m.div>

      {/* Projects Grid Content */}
      {data.items.length === 0 ? (
        <m.div
          variants={itemVariants}
          className="flex flex-1 flex-col items-center justify-center gap-3 rounded-3xl border border-border/50 bg-card/75 py-20 text-center backdrop-blur-xl shadow-lg"
        >
          <div className="flex size-14 items-center justify-center rounded-2xl bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
            <FolderKanban className="size-7" aria-hidden />
          </div>
          <h2 className="text-lg font-bold text-foreground">{t("empty.title")}</h2>
          <p className="max-w-sm text-sm text-muted-foreground">{t("empty.description")}</p>
        </m.div>
      ) : (
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
          {data.items.map((project) => (
            <m.div
              key={project.id}
              variants={itemVariants}
              whileHover={{ y: -4, scale: 1.01 }}
              transition={{ duration: 0.2 }}
              className="group relative flex flex-col justify-between overflow-hidden rounded-3xl border border-border/60 bg-card/80 p-6 backdrop-blur-xl transition-all duration-300 hover:border-emerald-500/40 hover:shadow-xl hover:shadow-emerald-500/5"
            >
              <div className="space-y-4">
                {/* Card Top: Icon, Title & Action Menu */}
                <div className="flex items-start justify-between gap-3">
                  <div className="flex items-center gap-3.5">
                    <div className="flex size-12 shrink-0 items-center justify-center rounded-2xl border border-emerald-500/30 bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 shadow-2xs group-hover:scale-105 transition-transform">
                      <FolderKanban className="size-6" />
                    </div>
                    <div className="overflow-hidden">
                      <Link
                        href={`${ROUTES.adminProjects}/${project.id}`}
                        className="block font-bold text-base text-foreground tracking-tight hover:text-emerald-600 dark:hover:text-emerald-400 transition-colors truncate"
                      >
                        {project.name}
                      </Link>
                      <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
                        <Sparkles className="size-3 text-emerald-500" />
                        {t("workspace")}
                      </span>
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex items-center gap-1 shrink-0 opacity-80 group-hover:opacity-100 transition-opacity">
                    <Can I={ACTIONS.UPDATE} a={RESOURCES.PROJECT}>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={(e) => {
                          e.preventDefault();
                          setFormTarget(project);
                        }}
                        className="size-8 p-0 text-muted-foreground hover:text-foreground cursor-pointer"
                        title={t("actions.edit")}
                      >
                        <Pencil className="size-3.5" />
                      </Button>
                    </Can>
                    <Can I={ACTIONS.DELETE} a={RESOURCES.PROJECT}>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={(e) => {
                          e.preventDefault();
                          setDeleteTarget(project);
                        }}
                        className="size-8 p-0 text-rose-600 hover:bg-rose-500/10 hover:text-rose-700 dark:hover:bg-rose-950/50 cursor-pointer"
                        title={t("actions.delete")}
                      >
                        <Trash2 className="size-3.5" />
                      </Button>
                    </Can>
                  </div>
                </div>

                {/* Description */}
                <p className="text-xs text-muted-foreground line-clamp-2 leading-relaxed min-h-[32px]">
                  {project.description || t("noDescription")}
                </p>
              </div>

              {/* Card Footer: Navigation link */}
              <div className="mt-6 pt-4 border-t border-border/40 flex items-center justify-between">
                <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <Layers className="size-3.5 text-emerald-500" />
                  <span>{t("environmentsAndConfig")}</span>
                </div>

                <Link
                  href={`${ROUTES.adminProjects}/${project.id}`}
                  className="inline-flex items-center gap-1 text-xs font-semibold text-emerald-600 dark:text-emerald-400 group-hover:translate-x-1 transition-transform"
                >
                  {t("actions.inspect")} <ArrowRight className="size-3.5" />
                </Link>
              </div>
            </m.div>
          ))}
        </div>
      )}

      {/* Form Dialog */}
      {formTarget !== null && (
        <ProjectFormDialog
          isOpen
          onClose={() => setFormTarget(null)}
          project={formTarget === "create" ? null : formTarget}
        />
      )}

      {/* Delete Dialog */}
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
    </m.div>
  );
}
