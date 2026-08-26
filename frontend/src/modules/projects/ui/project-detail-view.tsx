"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { Plus, Pencil, Trash2, Link2, Users } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { ConfirmDialog } from "@/shared/ui/confirm-dialog";
import { CanInProject, ProjectPermissionProvider } from "@/entities/permission";
import { ACTIONS, RESOURCES } from "@/shared/constants/permissions";
import { useProjectQuery } from "@/entities/project";
import { useProjectEnvironmentsQuery, type Environment } from "@/entities/environment";
import { fetchProjectLinks, fetchProjectMembers, type ProjectLink, type ProjectMember } from "../api/fetchers";
import { projectLinksKeys, projectMembersKeys } from "../api/query-keys";
import { useDeleteEnvironment } from "../hooks/use-delete-environment";
import { useDeleteProjectLink } from "../hooks/use-delete-project-link";
import { useRemoveProjectMember } from "../hooks/use-remove-project-member";
import { useAssignMemberProjectRole } from "../hooks/use-assign-member-project-role";
import { EnvironmentFormDialog } from "./environment-form-dialog";
import { ProjectLinkFormDialog } from "./project-link-form-dialog";
import { ProjectMemberFormDialog } from "./project-member-form-dialog";
import { ProjectRolesSection } from "./project-roles-section";
import { fetchProjectRoles } from "../api/fetchers";
import { projectRolesKeys } from "../api/query-keys";
import { IconDns, IconJira, IconGit, IconNotification, IconGrafana, IconServer } from "@/shared/ui/icons";

import { m, type Variants } from "@/shared/lib/motion";

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

const containerVariants: Variants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.08,
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

/**
 * useProjectEnvironmentsQuery is a Suspense query with no built-in "disabled"
 * mode, so this must stay unmounted (not just visually hidden) for a caller
 * without environment:read — gated via <CanInProject>'s children-as-ReactNode
 * prop in ProjectDetailView, never rendered directly.
 */
function EnvironmentsSection({
  projectId,
  onManageTunnels,
  onManageLogs,
  onManageAlerting,
}: {
  projectId: string;
  onManageTunnels: (environment: Environment) => void;
  onManageLogs: (environment: Environment) => void;
  onManageAlerting: (environment: Environment) => void;
}) {
  const t = useTranslations("projects");
  const { data: environments } = useProjectEnvironmentsQuery(projectId);
  const deleteEnvironment = useDeleteEnvironment(projectId);

  const [envFormTarget, setEnvFormTarget] = useState<Environment | "create" | null>(null);
  const [envDeleteTarget, setEnvDeleteTarget] = useState<Environment | null>(null);

  return (
    <>
      <m.section variants={itemVariants} className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <IconServer className="size-5 shrink-0 rounded-lg shadow-2xs" />
            <h2 className="text-sm font-bold uppercase tracking-wider text-muted-foreground">
              {t("sections.environments")} ({environments.length})
            </h2>
          </div>
          <CanInProject I={ACTIONS.CREATE} a={RESOURCES.ENVIRONMENT}>
            <Button
              size="sm"
              onClick={() => setEnvFormTarget("create")}
              className="gap-1.5 bg-gradient-to-r from-emerald-600 to-teal-600 font-semibold text-white shadow-xs hover:from-emerald-700 hover:to-teal-700"
            >
              <Plus className="size-3.5" /> {t("actions.addEnvironment")}
            </Button>
          </CanInProject>
        </div>

        {environments.length === 0 ? (
          <div className="flex flex-col items-center justify-center rounded-3xl border border-border/50 bg-card/60 py-12 text-center backdrop-blur-md">
            <p className="text-sm text-muted-foreground">{t("empty.environments")}</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {environments.map((env) => (
              <m.div
                key={env.id}
                whileHover={{ y: -3, scale: 1.01 }}
                transition={{ duration: 0.2 }}
                className="group relative flex flex-col justify-between rounded-2xl border border-border/60 bg-card/80 p-5 backdrop-blur-xl transition-all duration-300 hover:border-emerald-500/40 hover:shadow-lg hover:shadow-emerald-500/5"
              >
                <div>
                  {/* Env Top Header */}
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-500/30 bg-emerald-500/15 px-2.5 py-1 text-xs font-bold text-emerald-600 dark:text-emerald-400 uppercase tracking-wider">
                        <span className="relative flex size-2">
                          <span className="absolute inline-flex size-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                          <span className="relative inline-flex size-2 rounded-full bg-emerald-500" />
                        </span>
                        {t(`environmentTypes.${env.type}`)}
                      </span>
                      <h3 className="font-bold text-sm text-foreground truncate">{env.name}</h3>
                    </div>

                    <div className="flex items-center gap-1">
                      <CanInProject I={ACTIONS.UPDATE} a={RESOURCES.ENVIRONMENT}>
                        <button
                          type="button"
                          onClick={() => setEnvFormTarget(env)}
                          className="flex size-7 items-center justify-center rounded-lg text-muted-foreground hover:bg-muted hover:text-foreground cursor-pointer"
                          title={t("actions.edit")}
                        >
                          <Pencil className="size-3.5" />
                        </button>
                      </CanInProject>
                      <CanInProject I={ACTIONS.DELETE} a={RESOURCES.ENVIRONMENT}>
                        <button
                          type="button"
                          onClick={() => setEnvDeleteTarget(env)}
                          className="flex size-7 items-center justify-center rounded-lg text-rose-600 hover:bg-rose-500/10 hover:text-rose-700 dark:hover:bg-rose-950/50 cursor-pointer"
                          title={t("actions.delete")}
                        >
                          <Trash2 className="size-3.5" />
                        </button>
                      </CanInProject>
                    </div>
                  </div>

                  {/* High-Tech Operations Launch Buttons */}
                  <div className="mt-5 grid grid-cols-3 gap-2">
                    <CanInProject I={ACTIONS.READ} a={RESOURCES.PROJECT_CLOUDFLARE_TUNNEL}>
                      <button
                        type="button"
                        onClick={() => onManageTunnels(env)}
                        className="group/btn flex flex-col items-center justify-center gap-1.5 rounded-xl border border-blue-500/20 bg-blue-500/5 p-2.5 text-center transition-all hover:border-blue-500/40 hover:bg-blue-500/15 cursor-pointer"
                        title={t("actions.manageTunnels")}
                      >
                        <IconDns className="size-4.5 group-hover/btn:scale-110 transition-transform" />
                        <span className="text-[10px] font-bold text-blue-700 dark:text-blue-300 uppercase tracking-tight">
                          {t("edgeDns")}
                        </span>
                      </button>
                    </CanInProject>

                    <CanInProject I={ACTIONS.READ} a={RESOURCES.PROJECT_LOKI_CONFIG}>
                      <button
                        type="button"
                        onClick={() => onManageLogs(env)}
                        className="group/btn flex flex-col items-center justify-center gap-1.5 rounded-xl border border-purple-500/20 bg-purple-500/5 p-2.5 text-center transition-all hover:border-purple-500/40 hover:bg-purple-500/15 cursor-pointer"
                        title={t("actions.manageLogs")}
                      >
                        <IconGrafana className="size-4.5 group-hover/btn:scale-110 transition-transform" />
                        <span className="text-[10px] font-bold text-purple-700 dark:text-purple-300 uppercase tracking-tight">
                          {t("lokiLogs")}
                        </span>
                      </button>
                    </CanInProject>

                    <CanInProject I={ACTIONS.READ} a={RESOURCES.PROJECT_ALERT_RULE}>
                      <button
                        type="button"
                        onClick={() => onManageAlerting(env)}
                        className="group/btn flex flex-col items-center justify-center gap-1.5 rounded-xl border border-amber-500/20 bg-amber-500/5 p-2.5 text-center transition-all hover:border-amber-500/40 hover:bg-amber-500/15 cursor-pointer"
                        title={t("actions.manageAlerting")}
                      >
                        <IconNotification className="size-4.5 group-hover/btn:scale-110 transition-transform" />
                        <span className="text-[10px] font-bold text-amber-700 dark:text-amber-300 uppercase tracking-tight">
                          {t("alerts")}
                        </span>
                      </button>
                    </CanInProject>
                  </div>
                </div>
              </m.div>
            ))}
          </div>
        )}
      </m.section>

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
    </>
  );
}

/**
 * fetchProjectRoles is already scoped to `projectId`, so a role from a
 * different project can never appear as an option here.
 */
function MemberRoleSelect({ projectId, member }: { projectId: string; member: ProjectMember }) {
  const t = useTranslations("projects");
  const { data: roles = [] } = useQuery({
    queryKey: projectRolesKeys.forProject(projectId),
    queryFn: () => fetchProjectRoles(projectId),
  });
  const assignRole = useAssignMemberProjectRole(projectId);

  return (
    <select
      value={member.projectRoleId ?? ""}
      disabled={assignRole.isPending}
      onChange={(e) =>
        assignRole.mutate({ userId: member.userId, projectRoleId: e.target.value || null })
      }
      className="mt-1 h-7 max-w-[10rem] rounded-md border bg-background px-1.5 text-xs disabled:opacity-60"
    >
      <option value="">{t("members.noRole")}</option>
      {roles.map((role) => (
        <option key={role.id} value={role.id}>
          {role.name}
        </option>
      ))}
    </select>
  );
}

function EnvironmentsSectionNoPermission() {
  const t = useTranslations("projects");
  return (
    <m.section variants={itemVariants} className="space-y-4">
      <div className="flex items-center gap-2.5">
        <IconServer className="size-5 shrink-0 rounded-lg shadow-2xs" />
        <h2 className="text-sm font-bold uppercase tracking-wider text-muted-foreground">
          {t("sections.environments")}
        </h2>
      </div>
      <div className="flex flex-col items-center justify-center rounded-3xl border border-border/50 bg-card/60 py-12 text-center backdrop-blur-md">
        <p className="text-sm text-muted-foreground">{t("noPermission.environments")}</p>
      </div>
    </m.section>
  );
}

export function ProjectDetailView({
  projectId,
  onManageTunnels,
  onManageLogs,
  onManageAlerting,
  children,
}: {
  projectId: string;
  onManageTunnels: (environment: Environment) => void;
  onManageLogs: (environment: Environment) => void;
  onManageAlerting: (environment: Environment) => void;
  children?: React.ReactNode;
}) {
  const t = useTranslations("projects");
  const { data: project } = useProjectQuery(projectId);
  const { data: links = [] } = useQuery({
    queryKey: projectLinksKeys.forProject(projectId),
    queryFn: () => fetchProjectLinks(projectId),
  });
  const { data: members = [] } = useQuery({
    queryKey: projectMembersKeys.forProject(projectId),
    queryFn: () => fetchProjectMembers(projectId),
  });

  const deleteLink = useDeleteProjectLink(projectId);
  const removeMember = useRemoveProjectMember(projectId);

  const [linkFormTarget, setLinkFormTarget] = useState<ProjectLink | "create" | null>(null);
  const [linkDeleteTarget, setLinkDeleteTarget] = useState<ProjectLink | null>(null);
  const [memberFormOpen, setMemberFormOpen] = useState(false);
  const [memberRemoveTarget, setMemberRemoveTarget] = useState<ProjectMember | null>(null);

  return (
    <ProjectPermissionProvider projectId={projectId}>
    <m.div
      variants={containerVariants}
      initial="hidden"
      animate="visible"
      className="flex flex-1 flex-col gap-0 pb-10"
    >
      {/* ═══ 2-Column Grid: Main Content + Right Sidebar ═══ */}
      <div className="grid grid-cols-1 lg:grid-cols-[1fr_340px] items-start gap-6 xl:gap-8">

        {/* ─── LEFT: Main Content ─── */}
        <div className="flex flex-col gap-8 min-w-0">
          {/* 1. Hero Project Banner */}
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

          {/* 2. Environments Control Matrix */}
          <CanInProject I={ACTIONS.READ} a={RESOURCES.ENVIRONMENT} fallback={<EnvironmentsSectionNoPermission />}>
            <EnvironmentsSection
              projectId={projectId}
              onManageTunnels={onManageTunnels}
              onManageLogs={onManageLogs}
              onManageAlerting={onManageAlerting}
            />
          </CanInProject>

          {/* 3. Project Resources & Integrations Hub */}
          <m.section variants={itemVariants} className="space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Link2 className="size-4 text-primary" />
                <h2 className="text-sm font-bold uppercase tracking-wider text-muted-foreground">
                  {t("sections.links")} ({links.length})
                </h2>
              </div>
              <CanInProject I={ACTIONS.MANAGE} a={RESOURCES.PROJECT_LINK}>
                <Button size="sm" variant="outline" onClick={() => setLinkFormTarget("create")} className="gap-1.5 shadow-2xs">
                  <Plus className="size-3.5" /> {t("actions.addLink")}
                </Button>
              </CanInProject>
            </div>

            {links.length === 0 ? (
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

          {/* Injected sections (e.g. NotificationChannelsSection) */}
          {children}
        </div>

        {/* ─── RIGHT: Sticky Sidebar (Members + Project Roles) ─── */}
        <m.aside
          variants={itemVariants}
          className="flex flex-col gap-5 lg:sticky lg:top-0 lg:max-h-[calc(100vh-6rem)] lg:overflow-y-auto"
        >
          {/* Members Panel */}
          <div className="rounded-2xl border border-border/50 bg-card/80 backdrop-blur-xl shadow-sm overflow-hidden">
            {/* Members Header */}
            <div className="flex items-center justify-between border-b border-border/30 px-5 py-3.5">
              <div className="flex items-center gap-2">
                <Users className="size-4 text-primary" />
                <h2 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
                  {t("sections.members")} ({members.length})
                </h2>
              </div>
              <CanInProject I={ACTIONS.MANAGE} a={RESOURCES.PROJECT_MEMBER}>
                <button
                  type="button"
                  onClick={() => setMemberFormOpen(true)}
                  className="flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs font-semibold text-primary hover:bg-primary/10 transition-colors cursor-pointer"
                >
                  <Plus className="size-3" /> {t("actions.addMember")}
                </button>
              </CanInProject>
            </div>

            {/* Members List */}
            <div className="divide-y divide-border/20">
              {members.length === 0 ? (
                <div className="flex items-center justify-center py-10 px-5">
                  <p className="text-xs text-muted-foreground">{t("empty.members")}</p>
                </div>
              ) : (
                members.map((member) => (
                  <div
                    key={member.userId}
                    className="flex items-center gap-3 px-5 py-3 transition-colors hover:bg-muted/30"
                  >
                    {/* Avatar */}
                    <div className="flex size-8 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-blue-500 to-indigo-600 text-white text-[11px] font-bold shadow-sm">
                      {member.name
                        .split(" ")
                        .map((w) => w[0])
                        .join("")
                        .slice(0, 2)
                        .toUpperCase()}
                    </div>

                    {/* Info */}
                    <div className="flex flex-col min-w-0 flex-1">
                      <span className="text-sm font-semibold text-foreground truncate leading-tight">
                        {member.name}
                      </span>
                      <span className="text-[11px] text-muted-foreground truncate leading-tight">
                        {member.email}
                      </span>
                      <CanInProject
                        I={ACTIONS.MANAGE}
                        a={RESOURCES.PROJECT_MEMBER}
                        fallback={
                          <span className="mt-0.5 text-[11px] font-medium text-muted-foreground/80">
                            {member.projectRoleName ?? t("members.noRole")}
                          </span>
                        }
                      >
                        <MemberRoleSelect projectId={projectId} member={member} />
                      </CanInProject>
                    </div>

                    {/* Remove button */}
                    <CanInProject I={ACTIONS.MANAGE} a={RESOURCES.PROJECT_MEMBER}>
                      <button
                        type="button"
                        onClick={() => setMemberRemoveTarget(member)}
                        className="flex size-6 shrink-0 items-center justify-center rounded-md text-rose-500/70 hover:bg-rose-500/10 hover:text-rose-600 cursor-pointer transition-colors"
                        title={t("actions.removeMember")}
                      >
                        <Trash2 className="size-3" />
                      </button>
                    </CanInProject>
                  </div>
                ))
              )}
            </div>
          </div>

          <CanInProject I={ACTIONS.READ} a={RESOURCES.PROJECT_ROLE}>
            <ProjectRolesSection projectId={projectId} />
          </CanInProject>
        </m.aside>
      </div>

      {/* Dialogs — portaled, position-independent */}
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

      <ProjectMemberFormDialog
        isOpen={memberFormOpen}
        onClose={() => setMemberFormOpen(false)}
        projectId={projectId}
        excludeUserIds={new Set(members.map((m) => m.userId))}
      />
      <ConfirmDialog
        isOpen={memberRemoveTarget !== null}
        onClose={() => setMemberRemoveTarget(null)}
        onConfirm={() => {
          if (memberRemoveTarget) {
            removeMember.mutate(memberRemoveTarget.userId, {
              onSuccess: () => setMemberRemoveTarget(null),
            });
          }
        }}
        title={t("deleteConfirm.memberTitle")}
        description={t("deleteConfirm.memberDescription", { name: memberRemoveTarget?.name ?? "" })}
        isLoading={removeMember.isPending}
      />
    </m.div>
    </ProjectPermissionProvider>
  );
}
