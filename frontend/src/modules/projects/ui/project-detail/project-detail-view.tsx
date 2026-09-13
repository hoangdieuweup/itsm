"use client";

import { CanInProject, ProjectPermissionProvider } from "@/entities/permission";
import { ACTIONS, RESOURCES } from "@/shared/constants/permissions";
import { type Environment } from "@/entities/environment";
import { m } from "@/shared/lib/motion";
import { ProjectRolesSection } from "../project-roles-section";
import { EnvironmentsSection, EnvironmentsSectionNoPermission } from "./environments-section";
import { ProjectHero } from "./project-hero";
import { ProjectLinksSection } from "./project-links-section";
import { ProjectMembersPanel } from "./project-members-panel";
import { containerVariants, itemVariants } from "./motion-variants";

export function ProjectDetailView({
  projectId,
  onManageTunnels,
  onManageLoki,
  onManageAlerting,
  children,
}: {
  projectId: string;
  onManageTunnels: (environment: Environment) => void;
  onManageLoki: (environment: Environment) => void;
  onManageAlerting: (environment: Environment) => void;
  children?: React.ReactNode;
}) {
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
            <ProjectHero projectId={projectId} />

            <CanInProject
              I={ACTIONS.READ}
              a={RESOURCES.ENVIRONMENT}
              fallback={<EnvironmentsSectionNoPermission />}
            >
              <EnvironmentsSection
                projectId={projectId}
                onManageTunnels={onManageTunnels}
                onManageLoki={onManageLoki}
                onManageAlerting={onManageAlerting}
              />
            </CanInProject>

            <ProjectLinksSection projectId={projectId} />

            {/* Injected sections (e.g. NotificationChannelsSection) */}
            {children}
          </div>

          {/* ─── RIGHT: Sticky Sidebar (Members + Project Roles) ─── */}
          <m.aside
            variants={itemVariants}
            className="flex flex-col gap-5 lg:sticky lg:top-0 lg:max-h-[calc(100vh-6rem)] lg:overflow-y-auto"
          >
            <ProjectMembersPanel projectId={projectId} />

            <CanInProject I={ACTIONS.READ} a={RESOURCES.PROJECT_ROLE}>
              <ProjectRolesSection projectId={projectId} />
            </CanInProject>
          </m.aside>
        </div>
      </m.div>
    </ProjectPermissionProvider>
  );
}
