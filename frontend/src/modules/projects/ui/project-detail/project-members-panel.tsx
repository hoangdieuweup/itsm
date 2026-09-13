"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { Plus, Trash2, Users } from "lucide-react";
import { Skeleton } from "@/shared/ui/skeleton";
import { ConfirmDialog } from "@/shared/ui/confirm-dialog";
import { CanInProject } from "@/entities/permission";
import { ACTIONS, RESOURCES } from "@/shared/constants/permissions";
import { fetchProjectMembers, fetchProjectRoles, type ProjectMember } from "../../api/fetchers";
import { projectMembersKeys, projectRolesKeys } from "../../api/query-keys";
import { useRemoveProjectMember } from "../../hooks/use-remove-project-member";
import { useAssignMemberProjectRole } from "../../hooks/use-assign-member-project-role";
import { ProjectMemberFormDialog } from "../project-member-form-dialog";

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
      onChange={(e) => assignRole.mutate({ userId: member.userId, projectRoleId: e.target.value || null })}
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

export function ProjectMembersPanel({ projectId }: { projectId: string }) {
  const t = useTranslations("projects");
  const { data: members = [], isLoading: membersLoading } = useQuery({
    queryKey: projectMembersKeys.forProject(projectId),
    queryFn: () => fetchProjectMembers(projectId),
  });
  const removeMember = useRemoveProjectMember(projectId);

  const [memberFormOpen, setMemberFormOpen] = useState(false);
  const [memberRemoveTarget, setMemberRemoveTarget] = useState<ProjectMember | null>(null);

  return (
    <>
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
          {membersLoading ? (
            <div className="space-y-2 p-3">
              <Skeleton className="h-12 w-full rounded-xl" />
              <Skeleton className="h-12 w-full rounded-xl" />
            </div>
          ) : members.length === 0 ? (
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
    </>
  );
}
