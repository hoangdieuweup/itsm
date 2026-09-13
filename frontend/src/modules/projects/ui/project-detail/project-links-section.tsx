"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { Plus, Pencil, Trash2, Link2 } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { Skeleton } from "@/shared/ui/skeleton";
import { ConfirmDialog } from "@/shared/ui/confirm-dialog";
import { CanInProject } from "@/entities/permission";
import { ACTIONS, RESOURCES } from "@/shared/constants/permissions";
import { IconJira, IconGit } from "@/shared/ui/icons";
import { m } from "@/shared/lib/motion";
import { fetchProjectLinks } from "../../api/fetchers";
import type { ProjectLink } from "../../model/schema";
import { projectLinksKeys } from "../../api/query-keys";
import { useDeleteProjectLink } from "../../hooks/use-delete-project-link";
import { ProjectLinkFormDialog } from "../project-link-form-dialog";
import { itemVariants } from "./motion-variants";

function getLinkIcon(name: string, url: string) {
  const lower = `${name} ${url}`.toLowerCase();
  if (lower.includes("jira") || lower.includes("atlassian")) {
    return <IconJira size={18} />;
  }
  if (lower.includes("git") || lower.includes("github") || lower.includes("gitlab")) {
    return <IconGit size={18} />;
  }
  return <Link2 className="size-4 text-primary" />;
}

export function ProjectLinksSection({ projectId }: { projectId: string }) {
  const t = useTranslations("projects");
  const { data: links = [], isLoading: linksLoading } = useQuery({
    queryKey: projectLinksKeys.forProject(projectId),
    queryFn: () => fetchProjectLinks(projectId),
  });
  const deleteLink = useDeleteProjectLink(projectId);

  const [linkFormTarget, setLinkFormTarget] = useState<ProjectLink | "create" | null>(null);
  const [linkDeleteTarget, setLinkDeleteTarget] = useState<ProjectLink | null>(null);

  return (
    <>
      <m.section variants={itemVariants} className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Link2 className="size-4 text-primary" />
            <h2 className="text-sm font-bold uppercase tracking-wider text-muted-foreground">
              {t("sections.links")} ({links.length})
            </h2>
          </div>
          <CanInProject I={ACTIONS.MANAGE} a={RESOURCES.PROJECT_LINK}>
            <Button
              size="sm"
              variant="outline"
              onClick={() => setLinkFormTarget("create")}
              className="gap-1.5 shadow-2xs"
            >
              <Plus className="size-3.5" /> {t("actions.addLink")}
            </Button>
          </CanInProject>
        </div>

        {linksLoading ? (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Skeleton className="h-16 w-full rounded-2xl" />
            <Skeleton className="h-16 w-full rounded-2xl" />
          </div>
        ) : links.length === 0 ? (
          <div className="flex flex-col items-center justify-center rounded-3xl border border-border/50 bg-card/60 py-12 text-center backdrop-blur-md">
            <p className="text-sm text-muted-foreground">{t("empty.links")}</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            {links.map((link) => (
              <div
                key={link.id}
                className="flex items-center justify-between rounded-2xl border border-border/60 bg-card/70 p-4 backdrop-blur-md transition-all hover:border-primary/40 shadow-2xs"
              >
                <div className="flex items-center gap-3 overflow-hidden">
                  <div className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
                    {getLinkIcon(link.name, link.url)}
                  </div>
                  <div className="flex flex-col overflow-hidden">
                    <div className="flex items-center gap-1.5">
                      <span className="font-semibold text-sm text-foreground truncate">{link.name}</span>
                      {link.isDefault && (
                        <span className="rounded-md bg-blue-500/10 px-1.5 py-0.5 text-[9px] font-bold text-blue-600 uppercase dark:text-blue-400">
                          {t("badges.default")}
                        </span>
                      )}
                    </div>
                    <a
                      href={link.url}
                      target="_blank"
                      rel="noreferrer"
                      className="font-mono text-xs text-muted-foreground truncate hover:text-primary hover:underline"
                    >
                      {link.url}
                    </a>
                  </div>
                </div>

                <CanInProject I={ACTIONS.MANAGE} a={RESOURCES.PROJECT_LINK}>
                  <div className="flex items-center gap-1 shrink-0 ml-2">
                    <button
                      type="button"
                      onClick={() => setLinkFormTarget(link)}
                      className="flex size-7 items-center justify-center rounded-lg text-muted-foreground hover:bg-muted hover:text-foreground cursor-pointer"
                      title={t("actions.edit")}
                    >
                      <Pencil className="size-3.5" />
                    </button>
                    <button
                      type="button"
                      onClick={() => setLinkDeleteTarget(link)}
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
        )}
      </m.section>

      {linkFormTarget !== null && (
        <ProjectLinkFormDialog
          isOpen
          onClose={() => setLinkFormTarget(null)}
          projectId={projectId}
          link={linkFormTarget === "create" ? null : linkFormTarget}
        />
      )}
      <ConfirmDialog
        isOpen={linkDeleteTarget !== null}
        onClose={() => setLinkDeleteTarget(null)}
        onConfirm={() => {
          if (linkDeleteTarget) {
            deleteLink.mutate(linkDeleteTarget.id, { onSuccess: () => setLinkDeleteTarget(null) });
          }
        }}
        title={t("deleteConfirm.linkTitle")}
        description={t("deleteConfirm.linkDescription", { name: linkDeleteTarget?.name ?? "" })}
        isLoading={deleteLink.isPending}
      />
    </>
  );
}
