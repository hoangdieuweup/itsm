"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { Plus, Pencil, Trash2, Server, Link2, Globe, Waypoints, ScrollText, Siren } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { ConfirmDialog } from "@/shared/ui/confirm-dialog";
import { Link } from "@/shared/lib/i18n/navigation";
import { Can } from "@/entities/permission";
import { ACTIONS, RESOURCES } from "@/shared/constants/permissions";
import { useProjectQuery } from "@/entities/project";
import { useProjectEnvironmentsQuery, type Environment } from "@/entities/environment";
import { fetchProjectLinks, type ProjectLink } from "../api/fetchers";
import { projectLinksKeys } from "../api/query-keys";
import { useDeleteEnvironment } from "../hooks/use-delete-environment";
import { useDeleteProjectLink } from "../hooks/use-delete-project-link";
import { EnvironmentFormDialog } from "./environment-form-dialog";
import { ProjectLinkFormDialog } from "./project-link-form-dialog";

export function ProjectDetailView({
  projectId,
  onManageDns,
  onManageTunnels,
  onManageLogs,
}: {
  projectId: string;
  /** Opens the environment's DNS management inline instead of navigating away. */
  onManageDns: (environment: Environment) => void;
  /** Opens the environment's Tunnels management inline instead of navigating away. */
  onManageTunnels: (environment: Environment) => void;
  /** Opens the environment's Log Viewer inline instead of navigating away. */
  onManageLogs: (environment: Environment) => void;
}) {
  const t = useTranslations("projects");
  const { data: project } = useProjectQuery(projectId);
  const { data: environments } = useProjectEnvironmentsQuery(projectId);
  const { data: links = [] } = useQuery({
    queryKey: projectLinksKeys.forProject(projectId),
    queryFn: () => fetchProjectLinks(projectId),
  });

  const deleteEnvironment = useDeleteEnvironment(projectId);
  const deleteLink = useDeleteProjectLink(projectId);

  const [envFormTarget, setEnvFormTarget] = useState<Environment | "create" | null>(null);
  const [envDeleteTarget, setEnvDeleteTarget] = useState<Environment | null>(null);
  const [linkFormTarget, setLinkFormTarget] = useState<ProjectLink | "create" | null>(null);
  const [linkDeleteTarget, setLinkDeleteTarget] = useState<ProjectLink | null>(null);

  return (
    <div className="flex flex-1 flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-xl font-bold text-foreground">{project.name}</h1>
        {project.description && <p className="text-sm text-muted-foreground">{project.description}</p>}
      </div>

      <section className="flex flex-col gap-3 rounded-xl border bg-card p-5">
        <div className="flex items-center justify-between">
          <h2 className="flex items-center gap-2 text-sm font-bold text-foreground">
            <Server className="size-4" /> {t("sections.environments")}
          </h2>
          <Can I={ACTIONS.CREATE} a={RESOURCES.ENVIRONMENT}>
            <Button size="sm" onClick={() => setEnvFormTarget("create")}>
              <Plus className="mr-1.5 size-3.5" /> {t("actions.addEnvironment")}
            </Button>
          </Can>
        </div>
        <div className="flex flex-wrap gap-2">
          {environments.length === 0 && (
            <p className="text-sm text-muted-foreground">{t("empty.environments")}</p>
          )}
          {environments.map((env) => (
            <div
              key={env.id}
              className="flex items-center gap-2 rounded-lg border bg-muted/30 px-3 py-2 text-sm"
            >
              <span className="font-semibold uppercase tracking-wide text-foreground">
                {t(`environmentTypes.${env.type}`)}
              </span>
              <span className="text-muted-foreground">{env.name}</span>
              <Can I={ACTIONS.VIEW} a={RESOURCES.CLOUDFLARE_ACCOUNT}>
                <button
                  type="button"
                  onClick={() => onManageDns(env)}
                  className="cursor-pointer text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                  aria-label={t("actions.manageDns")}
                >
                  <Globe className="size-3.5" />
                </button>
              </Can>
              <Can I={ACTIONS.VIEW} a={RESOURCES.CLOUDFLARE_ACCOUNT}>
                <button
                  type="button"
                  onClick={() => onManageTunnels(env)}
                  className="cursor-pointer text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                  aria-label={t("actions.manageTunnels")}
                >
                  <Waypoints className="size-3.5" />
                </button>
              </Can>
              <Can I={ACTIONS.READ} a={RESOURCES.ENVIRONMENT}>
                <button
                  type="button"
                  onClick={() => onManageLogs(env)}
                  className="cursor-pointer text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                  aria-label={t("actions.manageLogs")}
                >
                  <ScrollText className="size-3.5" />
                </button>
              </Can>
              <Can I={ACTIONS.READ} a={RESOURCES.ALERT_RULE}>
                <Link
                  href={`/admin/environments/${env.id}/alerting`}
                  className="text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                  aria-label={t("actions.manageAlerting")}
                >
                  <Siren className="size-3.5" />
                </Link>
              </Can>
              <Can I={ACTIONS.UPDATE} a={RESOURCES.ENVIRONMENT}>
                <button
                  type="button"
                  onClick={() => setEnvFormTarget(env)}
                  className="cursor-pointer text-muted-foreground hover:text-foreground"
                >
                  <Pencil className="size-3.5" />
                </button>
              </Can>
              <Can I={ACTIONS.DELETE} a={RESOURCES.ENVIRONMENT}>
                <button
                  type="button"
                  onClick={() => setEnvDeleteTarget(env)}
                  className="cursor-pointer text-muted-foreground hover:text-destructive"
                >
                  <Trash2 className="size-3.5" />
                </button>
              </Can>
            </div>
          ))}
        </div>
      </section>

      <section className="flex flex-col gap-3 rounded-xl border bg-card p-5">
        <div className="flex items-center justify-between">
          <h2 className="flex items-center gap-2 text-sm font-bold text-foreground">
            <Link2 className="size-4" /> {t("sections.links")}
          </h2>
          <Can I={ACTIONS.UPDATE} a={RESOURCES.PROJECT}>
            <Button size="sm" onClick={() => setLinkFormTarget("create")}>
              <Plus className="mr-1.5 size-3.5" /> {t("actions.addLink")}
            </Button>
          </Can>
        </div>
        <div className="flex flex-col divide-y">
          {links.length === 0 && <p className="text-sm text-muted-foreground">{t("empty.links")}</p>}
          {links.map((link) => (
            <div key={link.id} className="flex items-center justify-between py-2 text-sm">
              <div className="flex items-center gap-2">
                <span className="font-medium text-foreground">{link.name}</span>
                {link.isDefault && (
                  <span className="rounded-full bg-blue-50 px-2 py-0.5 text-[10px] font-bold uppercase text-blue-700 dark:bg-blue-950/60 dark:text-blue-300">
                    {t("badges.default")}
                  </span>
                )}
                <a
                  href={link.url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-muted-foreground hover:underline"
                >
                  {link.url}
                </a>
              </div>
              <Can I={ACTIONS.UPDATE} a={RESOURCES.PROJECT}>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => setLinkFormTarget(link)}
                    className="cursor-pointer text-muted-foreground hover:text-foreground"
                  >
                    <Pencil className="size-3.5" />
                  </button>
                  <button
                    type="button"
                    onClick={() => setLinkDeleteTarget(link)}
                    className="cursor-pointer text-muted-foreground hover:text-destructive"
                  >
                    <Trash2 className="size-3.5" />
                  </button>
                </div>
              </Can>
            </div>
          ))}
        </div>
      </section>

      {envFormTarget !== null && (
        <EnvironmentFormDialog
          isOpen
          onClose={() => setEnvFormTarget(null)}
          projectId={projectId}
          environment={envFormTarget === "create" ? null : envFormTarget}
          existingTypes={environments.map((e) => e.type)}
        />
      )}
      <ConfirmDialog
        isOpen={envDeleteTarget !== null}
        onClose={() => setEnvDeleteTarget(null)}
        onConfirm={() => {
          if (envDeleteTarget) {
            deleteEnvironment.mutate(envDeleteTarget.id, { onSuccess: () => setEnvDeleteTarget(null) });
          }
        }}
        title={t("deleteConfirm.environmentTitle")}
        description={t("deleteConfirm.environmentDescription", { name: envDeleteTarget?.name ?? "" })}
        isLoading={deleteEnvironment.isPending}
      />

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
    </div>
  );
}
