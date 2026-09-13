"use client";

import { useTranslations } from "next-intl";
import { useProjectQuery } from "@/entities/project";
import { m } from "@/shared/lib/motion";
import { itemVariants } from "./motion-variants";

export function ProjectHero({ projectId }: { projectId: string }) {
  const t = useTranslations("projects");
  const { data: project } = useProjectQuery(projectId);

  return (
    <m.div
      variants={itemVariants}
      className="relative overflow-hidden rounded-3xl border border-border/60 bg-gradient-to-br from-emerald-500/10 via-teal-500/5 to-card/95 p-6 sm:p-8 backdrop-blur-2xl shadow-xl shadow-black/5 dark:shadow-black/20"
    >
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-6">
        <div className="flex items-start gap-4">
          <div className="flex size-14 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-emerald-500 to-teal-600 text-white font-black text-2xl shadow-lg shadow-emerald-500/25 ring-4 ring-emerald-500/10">
            {project.name.slice(0, 2).toUpperCase()}
          </div>
          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-500/30 bg-emerald-500/15 px-3 py-0.5 text-xs font-bold text-emerald-600 dark:text-emerald-400">
                <span className="relative flex size-2">
                  <span className="absolute inline-flex size-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                  <span className="relative inline-flex size-2 rounded-full bg-emerald-500" />
                </span>
                {t("activeWorkspace")}
              </span>
            </div>
            <h1 className="text-2xl font-extrabold tracking-tight text-foreground sm:text-3xl">
              {project.name}
            </h1>
            <p className="max-w-2xl text-sm text-muted-foreground leading-relaxed">
              {project.description || t("heroDescription")}
            </p>
          </div>
        </div>
      </div>
    </m.div>
  );
}
