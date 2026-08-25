"use client";

import { useTranslations } from "next-intl";
import {
  ArrowRight,
  Sparkles,
  Activity,
  Zap,
} from "lucide-react";
import { Link } from "@/shared/lib/i18n/navigation";
import { ROUTES } from "@/shared/constants/routes";
import { Can, RESOURCES, ACTIONS } from "@/entities/permission";
import { useAuthSession } from "@/modules/auth";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/shared/ui/card";
import { m, type Variants } from "@/shared/lib/motion";
import {
  IconCloudflare,
  IconAuditLogs,
  IconProject,
  IconUsers,
  IconPermission,
  IconNotification,
} from "@/shared/ui/icons";

const containerVariants: Variants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.08,
      delayChildren: 0.05,
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

export default function DashboardPage() {
  const { data: session } = useAuthSession();
  const tm = useTranslations("common.meta");
  const td = useTranslations("common.dashboard");
  const userName = session.user?.name ?? "Operator";
  const userRole = session.roleName ? session.roleName.toUpperCase() : "MEMBER";

  return (
    <m.div
      variants={containerVariants}
      initial="hidden"
      animate="visible"
      className="flex flex-1 flex-col gap-8 pb-10"
    >
      {/* 1. Hero Ops Banner */}
      <m.div
        variants={itemVariants}
        className="relative overflow-hidden rounded-3xl border border-border/50 bg-gradient-to-br from-blue-600/10 via-indigo-600/5 to-card/90 p-6 sm:p-8 backdrop-blur-xl shadow-lg shadow-black/5 dark:shadow-black/20"
      >
        <div className="absolute -right-16 -top-16 size-64 rounded-full bg-blue-500/10 blur-3xl" aria-hidden />
        <div className="absolute right-32 -bottom-16 size-48 rounded-full bg-indigo-500/10 blur-2xl" aria-hidden />

        <div className="relative z-10 flex flex-col md:flex-row md:items-center md:justify-between gap-6">
          <div className="space-y-2.5">
            <div className="flex flex-wrap items-center gap-2.5">
              <span className="inline-flex items-center gap-1.5 rounded-full border border-blue-500/30 bg-blue-500/15 px-3 py-1 text-xs font-bold text-blue-600 dark:text-blue-400 shadow-2xs">
                <Sparkles className="size-3.5" />
                {userRole}
              </span>
              <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-500/30 bg-emerald-500/15 px-3 py-1 text-xs font-medium text-emerald-600 dark:text-emerald-400">
                <span className="relative flex size-2">
                  <span className="absolute inline-flex size-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                  <span className="relative inline-flex size-2 rounded-full bg-emerald-500" />
                </span>
                {td("systemStatus")}: Operational
              </span>
            </div>
            <h1 className="text-2xl font-extrabold tracking-tight text-foreground sm:text-3xl lg:text-4xl">
              {td("welcomeBack", { name: userName })}
            </h1>
            <p className="max-w-2xl text-sm text-muted-foreground leading-relaxed">
              {tm("appDescription")}
            </p>
          </div>

          <div className="flex items-center gap-3 shrink-0">
            <div className="flex flex-col items-start md:items-end rounded-2xl border border-border/60 bg-card/60 px-4 py-3 backdrop-blur-md">
              <span className="text-[11px] font-semibold text-muted-foreground uppercase tracking-wider">
                ITSM Platform
              </span>
              <span className="font-mono text-sm font-bold text-foreground">
                v2.5.0 <span className="text-emerald-500 text-xs font-normal">● Live</span>
              </span>
            </div>
          </div>
        </div>
      </m.div>

      {/* 2. Real-time Telemetry Stats Grid */}
      <div>
        <div className="flex items-center justify-between pb-3">
          <div className="flex items-center gap-2">
            <Activity className="size-4 text-primary" />
            <h2 className="text-sm font-bold uppercase tracking-wider text-muted-foreground">
              {td("telemetry")}
            </h2>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {/* Card 1: Cloudflare */}
          <m.div variants={itemVariants} whileHover={{ y: -3, scale: 1.01 }} transition={{ duration: 0.2 }}>
            <Link href={ROUTES.adminCloudflareAccounts} className="block h-full">
              <Card className="h-full border-border/60 bg-card/75 backdrop-blur-md transition-all duration-300 hover:border-blue-500/40 hover:shadow-lg hover:shadow-blue-500/5">
                <CardHeader className="pb-2">
                  <div className="flex items-center justify-between">
                    <IconCloudflare className="size-10 shrink-0 rounded-xl shadow-xs" />
                    <span className="rounded-full bg-blue-50 px-2 py-0.5 text-[10px] font-bold text-blue-600 dark:bg-blue-950/60 dark:text-blue-300">
                      Edge Network
                    </span>
                  </div>
                  <CardTitle className="mt-3 text-base font-bold text-foreground">
                    {td("stats.cloudflareAccounts")}
                  </CardTitle>
                  <CardDescription className="text-xs">
                    {td("stats.cloudflareDesc")}
                  </CardDescription>
                </CardHeader>
                <CardContent className="pt-2">
                  <div className="flex items-center justify-between text-xs text-muted-foreground font-mono">
                    <span>Zones & Tunnels</span>
                    <span className="flex items-center text-blue-600 dark:text-blue-400 font-semibold group-hover:translate-x-0.5 transition-transform">
                      Inspect <ArrowRight className="ml-1 size-3" />
                    </span>
                  </div>
                </CardContent>
              </Card>
            </Link>
          </m.div>

          {/* Card 2: Incidents */}
          <m.div variants={itemVariants} whileHover={{ y: -3, scale: 1.01 }} transition={{ duration: 0.2 }}>
            <Link href={ROUTES.adminIncidents} className="block h-full">
              <Card className="h-full border-border/60 bg-card/75 backdrop-blur-md transition-all duration-300 hover:border-rose-500/40 hover:shadow-lg hover:shadow-rose-500/5">
                <CardHeader className="pb-2">
                  <div className="flex items-center justify-between">
                    <IconNotification className="size-10 shrink-0 rounded-xl shadow-xs" />
                    <span className="rounded-full bg-amber-50 px-2 py-0.5 text-[10px] font-bold text-amber-600 dark:bg-amber-950/60 dark:text-amber-300">
                      Real-time
                    </span>
                  </div>
                  <CardTitle className="mt-3 text-base font-bold text-foreground">
                    {td("stats.activeIncidents")}
                  </CardTitle>
                  <CardDescription className="text-xs">
                    {td("stats.incidentsDesc")}
                  </CardDescription>
                </CardHeader>
                <CardContent className="pt-2">
                  <div className="flex items-center justify-between text-xs text-muted-foreground font-mono">
                    <span>Resolution Hub</span>
                    <span className="flex items-center text-rose-600 dark:text-rose-400 font-semibold">
                      Control <ArrowRight className="ml-1 size-3" />
                    </span>
                  </div>
                </CardContent>
              </Card>
            </Link>
          </m.div>

          {/* Card 3: Projects & Environments */}
          <m.div variants={itemVariants} whileHover={{ y: -3, scale: 1.01 }} transition={{ duration: 0.2 }}>
            <Link href={ROUTES.adminProjects} className="block h-full">
              <Card className="h-full border-border/60 bg-card/75 backdrop-blur-md transition-all duration-300 hover:border-emerald-500/40 hover:shadow-lg hover:shadow-emerald-500/5">
                <CardHeader className="pb-2">
                  <div className="flex items-center justify-between">
                    <IconProject className="size-10 shrink-0 rounded-xl shadow-xs" />
                    <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-bold text-emerald-600 dark:bg-emerald-950/60 dark:text-emerald-300">
                      Workspaces
                    </span>
                  </div>
                  <CardTitle className="mt-3 text-base font-bold text-foreground">
                    {td("stats.activeProjects")}
                  </CardTitle>
                  <CardDescription className="text-xs">
                    {td("stats.projectsDesc")}
                  </CardDescription>
                </CardHeader>
                <CardContent className="pt-2">
                  <div className="flex items-center justify-between text-xs text-muted-foreground font-mono">
                    <span>DEV / STG / PROD</span>
                    <span className="flex items-center text-emerald-600 dark:text-emerald-400 font-semibold">
                      Manage <ArrowRight className="ml-1 size-3" />
                    </span>
                  </div>
                </CardContent>
              </Card>
            </Link>
          </m.div>

          {/* Card 4: Security & Audit Log */}
          <m.div variants={itemVariants} whileHover={{ y: -3, scale: 1.01 }} transition={{ duration: 0.2 }}>
            <Link href={ROUTES.adminAuditLog} className="block h-full">
              <Card className="h-full border-border/60 bg-card/75 backdrop-blur-md transition-all duration-300 hover:border-purple-500/40 hover:shadow-lg hover:shadow-purple-500/5">
                <CardHeader className="pb-2">
                  <div className="flex items-center justify-between">
                    <IconAuditLogs className="size-10 shrink-0 rounded-xl shadow-xs" />
                    <span className="rounded-full bg-purple-50 px-2 py-0.5 text-[10px] font-bold text-purple-600 dark:bg-purple-950/60 dark:text-purple-300">
                      Audit Stream
                    </span>
                  </div>
                  <CardTitle className="mt-3 text-base font-bold text-foreground">
                    {td("stats.securityAudit")}
                  </CardTitle>
                  <CardDescription className="text-xs">
                    {td("stats.securityDesc")}
                  </CardDescription>
                </CardHeader>
                <CardContent className="pt-2">
                  <div className="flex items-center justify-between text-xs text-muted-foreground font-mono">
                    <span>MongoDB Trail</span>
                    <span className="flex items-center text-purple-600 dark:text-purple-400 font-semibold">
                      Review <ArrowRight className="ml-1 size-3" />
                    </span>
                  </div>
                </CardContent>
              </Card>
            </Link>
          </m.div>
        </div>
      </div>

      {/* 3. Operations Quick Launchpad Grid */}
      <div>
        <div className="flex items-center justify-between pb-3">
          <div className="flex items-center gap-2">
            <Zap className="size-4 text-amber-500" />
            <h2 className="text-sm font-bold uppercase tracking-wider text-muted-foreground">
              {td("quickLaunchpad")}
            </h2>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {/* Action 1: Users */}
          <Can I={ACTIONS.READ} a={RESOURCES.USER}>
            <m.div variants={itemVariants} whileHover={{ y: -2, scale: 1.01 }} whileTap={{ scale: 0.99 }}>
              <Link href={ROUTES.adminUsers} className="group block h-full">
                <div className="flex items-center gap-4 rounded-2xl border border-border/60 bg-card/60 p-4.5 backdrop-blur-md transition-all duration-300 hover:border-primary/50 hover:bg-card hover:shadow-md shadow-2xs">
                  <IconUsers className="size-12 shrink-0 rounded-xl shadow-xs group-hover:scale-105 transition-transform" />
                  <div className="flex-1 overflow-hidden">
                    <h3 className="text-sm font-bold text-foreground truncate group-hover:text-primary transition-colors">
                      {td("actions.manageUsers")}
                    </h3>
                    <p className="text-xs text-muted-foreground truncate mt-0.5">
                      {td("userManagementDesc")}
                    </p>
                  </div>
                  <ArrowRight className="size-4 shrink-0 text-muted-foreground/60 transition-transform duration-200 group-hover:translate-x-1 group-hover:text-primary" />
                </div>
              </Link>
            </m.div>
          </Can>

          {/* Action 2: Roles */}
          <Can I={ACTIONS.READ} a={RESOURCES.ROLE}>
            <m.div variants={itemVariants} whileHover={{ y: -2, scale: 1.01 }} whileTap={{ scale: 0.99 }}>
              <Link href={ROUTES.adminRoles} className="group block h-full">
                <div className="flex items-center gap-4 rounded-2xl border border-border/60 bg-card/60 p-4.5 backdrop-blur-md transition-all duration-300 hover:border-purple-500/50 hover:bg-card hover:shadow-md shadow-2xs">
                  <IconPermission className="size-12 shrink-0 rounded-xl shadow-xs group-hover:scale-105 transition-transform" />
                  <div className="flex-1 overflow-hidden">
                    <h3 className="text-sm font-bold text-foreground truncate group-hover:text-purple-600 dark:group-hover:text-purple-400 transition-colors">
                      {td("actions.manageRoles")}
                    </h3>
                    <p className="text-xs text-muted-foreground truncate mt-0.5">
                      {td("roleManagementDesc")}
                    </p>
                  </div>
                  <ArrowRight className="size-4 shrink-0 text-muted-foreground/60 transition-transform duration-200 group-hover:translate-x-1 group-hover:text-purple-500" />
                </div>
              </Link>
            </m.div>
          </Can>

          {/* Action 3: Projects */}
          <Can I={ACTIONS.READ} a={RESOURCES.PROJECT}>
            <m.div variants={itemVariants} whileHover={{ y: -2, scale: 1.01 }} whileTap={{ scale: 0.99 }}>
              <Link href={ROUTES.adminProjects} className="group block h-full">
                <div className="flex items-center gap-4 rounded-2xl border border-border/60 bg-card/60 p-4.5 backdrop-blur-md transition-all duration-300 hover:border-emerald-500/50 hover:bg-card hover:shadow-md shadow-2xs">
                  <IconProject className="size-12 shrink-0 rounded-xl shadow-xs group-hover:scale-105 transition-transform" />
                  <div className="flex-1 overflow-hidden">
                    <h3 className="text-sm font-bold text-foreground truncate group-hover:text-emerald-600 dark:group-hover:text-emerald-400 transition-colors">
                      {td("actions.manageProjects")}
                    </h3>
                    <p className="text-xs text-muted-foreground truncate mt-0.5">
                      Workspaces & Environments
                    </p>
                  </div>
                  <ArrowRight className="size-4 shrink-0 text-muted-foreground/60 transition-transform duration-200 group-hover:translate-x-1 group-hover:text-emerald-500" />
                </div>
              </Link>
            </m.div>
          </Can>

          {/* Action 4: Cloudflare */}
          <Can I={ACTIONS.VIEW} a={RESOURCES.CLOUDFLARE_ACCOUNT}>
            <m.div variants={itemVariants} whileHover={{ y: -2, scale: 1.01 }} whileTap={{ scale: 0.99 }}>
              <Link href={ROUTES.adminCloudflareAccounts} className="group block h-full">
                <div className="flex items-center gap-4 rounded-2xl border border-border/60 bg-card/60 p-4.5 backdrop-blur-md transition-all duration-300 hover:border-blue-500/50 hover:bg-card hover:shadow-md shadow-2xs">
                  <IconCloudflare className="size-12 shrink-0 rounded-xl shadow-xs group-hover:scale-105 transition-transform" />
                  <div className="flex-1 overflow-hidden">
                    <h3 className="text-sm font-bold text-foreground truncate group-hover:text-blue-600 dark:group-hover:text-blue-400 transition-colors">
                      {td("actions.manageCloudflare")}
                    </h3>
                    <p className="text-xs text-muted-foreground truncate mt-0.5">
                      Zones, DNS, and Cloudflare Tunnels
                    </p>
                  </div>
                  <ArrowRight className="size-4 shrink-0 text-muted-foreground/60 transition-transform duration-200 group-hover:translate-x-1 group-hover:text-blue-500" />
                </div>
              </Link>
            </m.div>
          </Can>

          {/* Action 5: Incidents */}
          <Can I={ACTIONS.READ} a={RESOURCES.INCIDENT}>
            <m.div variants={itemVariants} whileHover={{ y: -2, scale: 1.01 }} whileTap={{ scale: 0.99 }}>
              <Link href={ROUTES.adminIncidents} className="group block h-full">
                <div className="flex items-center gap-4 rounded-2xl border border-border/60 bg-card/60 p-4.5 backdrop-blur-md transition-all duration-300 hover:border-amber-500/50 hover:bg-card hover:shadow-md shadow-2xs">
                  <IconNotification className="size-12 shrink-0 rounded-xl shadow-xs group-hover:scale-105 transition-transform" />
                  <div className="flex-1 overflow-hidden">
                    <h3 className="text-sm font-bold text-foreground truncate group-hover:text-amber-600 dark:group-hover:text-amber-400 transition-colors">
                      {td("actions.viewIncidents")}
                    </h3>
                    <p className="text-xs text-muted-foreground truncate mt-0.5">
                      Live alerts & triage control
                    </p>
                  </div>
                  <ArrowRight className="size-4 shrink-0 text-muted-foreground/60 transition-transform duration-200 group-hover:translate-x-1 group-hover:text-amber-500" />
                </div>
              </Link>
            </m.div>
          </Can>

          {/* Action 6: Audit Log */}
          <Can I={ACTIONS.READ} a={RESOURCES.AUDIT_LOG}>
            <m.div variants={itemVariants} whileHover={{ y: -2, scale: 1.01 }} whileTap={{ scale: 0.99 }}>
              <Link href={ROUTES.adminAuditLog} className="group block h-full">
                <div className="flex items-center gap-4 rounded-2xl border border-border/60 bg-card/60 p-4.5 backdrop-blur-md transition-all duration-300 hover:border-purple-500/50 hover:bg-card hover:shadow-md shadow-2xs">
                  <IconAuditLogs className="size-12 shrink-0 rounded-xl shadow-xs group-hover:scale-105 transition-transform" />
                  <div className="flex-1 overflow-hidden">
                    <h3 className="text-sm font-bold text-foreground truncate group-hover:text-purple-600 dark:group-hover:text-purple-400 transition-colors">
                      {td("actions.viewAuditLog")}
                    </h3>
                    <p className="text-xs text-muted-foreground truncate mt-0.5">
                      Immutable activity audit records
                    </p>
                  </div>
                  <ArrowRight className="size-4 shrink-0 text-muted-foreground/60 transition-transform duration-200 group-hover:translate-x-1 group-hover:text-purple-500" />
                </div>
              </Link>
            </m.div>
          </Can>
        </div>
      </div>
    </m.div>
  );
}

