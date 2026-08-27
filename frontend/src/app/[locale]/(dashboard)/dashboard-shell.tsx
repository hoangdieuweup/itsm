"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Menu, ChevronLeft, Activity } from "lucide-react";
import { Link, usePathname } from "@/shared/lib/i18n/navigation";
import { ROUTES } from "@/shared/constants/routes";
import { DashboardSidebar } from "./dashboard-sidebar";
import { UserMenu } from "@/modules/auth";
import { m } from "@/shared/lib/motion";

interface DashboardShellProps {
  children: React.ReactNode;
}

interface Breadcrumb {
  currentLabel: string;
  parentLabel?: string;
  parentHref?: string;
}

type NavTranslate = ReturnType<typeof useTranslations<"common.nav">>;

/**
 * Nested pages, which carry a back link to their list page.
 * Order matters: the `/logs` rule must be checked before the generic project
 * detail rule, otherwise a log page resolves as a plain detail page.
 */
function detailBreadcrumb(pathname: string, t: NavTranslate): Breadcrumb | null {
  if (
    pathname.startsWith(ROUTES.adminCloudflareAccounts) &&
    pathname !== ROUTES.adminCloudflareAccounts
  ) {
    return {
      currentLabel: t("detail"),
      parentLabel: t("cloudflareAccounts"),
      parentHref: ROUTES.adminCloudflareAccounts,
    };
  }
  if (pathname.startsWith(ROUTES.adminEnvironments)) {
    return {
      currentLabel: t("environments"),
      parentLabel: t("cloudflareAccounts"),
      parentHref: ROUTES.adminCloudflareAccounts,
    };
  }
  if (pathname.startsWith(ROUTES.adminProjects) && pathname.includes("/logs")) {
    const segments = pathname.split("/");
    const projectId = segments[segments.indexOf("projects") + 1];
    return {
      currentLabel: t("logs"),
      parentLabel: t("detail"),
      parentHref: `${ROUTES.adminProjects}/${projectId}`,
    };
  }
  if (pathname.startsWith(ROUTES.adminProjects) && pathname !== ROUTES.adminProjects) {
    return {
      currentLabel: t("detail"),
      parentLabel: t("projects"),
      parentHref: ROUTES.adminProjects,
    };
  }
  if (pathname.startsWith(ROUTES.adminIncidents) && pathname !== ROUTES.adminIncidents) {
    return {
      currentLabel: t("detail"),
      parentLabel: t("incidents"),
      parentHref: ROUTES.adminIncidents,
    };
  }
  return null;
}

/** Top-level list pages — no back link. */
function listBreadcrumb(pathname: string, t: NavTranslate): Breadcrumb | null {
  if (pathname.startsWith(ROUTES.adminUsers)) return { currentLabel: t("users") };
  if (pathname.startsWith(ROUTES.adminRoles)) return { currentLabel: t("roles") };
  if (pathname === ROUTES.adminProjects) return { currentLabel: t("projects") };
  if (pathname === ROUTES.adminAuditLog) return { currentLabel: t("auditLog") };
  if (pathname === ROUTES.adminCloudflareAccounts) return { currentLabel: t("cloudflareAccounts") };
  if (pathname === ROUTES.adminIncidents) return { currentLabel: t("incidents") };
  return null;
}

function resolveBreadcrumb(pathname: string, t: NavTranslate): Breadcrumb {
  return (
    detailBreadcrumb(pathname, t) ??
    listBreadcrumb(pathname, t) ?? { currentLabel: t("dashboard") }
  );
}

export function DashboardShell({ children }: DashboardShellProps) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const t = useTranslations("common.nav");
  const tm = useTranslations("common.meta");
  const td = useTranslations("common.dashboard");
  const pathname = usePathname();

  const breadcrumb = resolveBreadcrumb(pathname, t);

  return (
    <div className="relative flex h-screen w-full bg-background text-foreground selection:bg-primary/20 selection:text-primary overflow-hidden">
      {/* Background High-Tech Subtle Ambient Glow & Dot Grid */}
      <div
        className="pointer-events-none fixed inset-0 z-0 bg-[radial-gradient(#64748b_1px,transparent_1px)] [background-size:24px_24px] [mask-image:radial-gradient(ellipse_60%_50%_at_50%_0%,#000_70%,transparent_100%)] opacity-[0.04] dark:opacity-[0.08]"
        aria-hidden
      />
      <div
        className="pointer-events-none fixed -top-40 -left-40 z-0 size-96 rounded-full bg-blue-500/10 blur-3xl dark:bg-blue-600/10"
        aria-hidden
      />
      <div
        className="pointer-events-none fixed -top-40 right-0 z-0 size-96 rounded-full bg-indigo-500/10 blur-3xl dark:bg-indigo-600/10"
        aria-hidden
      />

      {/* 1. Permanent Desktop Sidebar & Mobile Slide-over Drawer */}
      <DashboardSidebar
        mobileOpen={mobileOpen}
        onMobileClose={() => setMobileOpen(false)}
      />

      {/* 2. Main Area (Header + Content) */}
      <div className="relative z-10 flex min-w-0 flex-1 flex-col h-screen overflow-hidden">
        {/* Top Navbar: Glassmorphic elevation */}
        <header className="sticky top-0 z-20 flex h-16 shrink-0 items-center justify-between border-b border-border/40 bg-background/80 px-4 shadow-xs backdrop-blur-xl sm:px-6 lg:px-8">
          {/* Left: Mobile hamburger & Breadcrumb Title */}
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => setMobileOpen(true)}
              aria-label={t("openMenu")}
              className="flex size-9 items-center justify-center rounded-xl border border-border/60 bg-card text-foreground shadow-2xs transition-all hover:border-primary/40 hover:bg-muted md:hidden cursor-pointer"
            >
              <Menu className="size-5" />
            </button>

            <nav className="flex items-center gap-2" aria-label={t("breadcrumb")}>
              <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground/70 hidden sm:inline">
                {tm("appName")}
              </span>
              <span className="text-muted-foreground/40 hidden sm:inline" aria-hidden>/</span>

              {breadcrumb.parentHref ? (
                <>
                  <Link
                    href={breadcrumb.parentHref}
                    className="group flex items-center gap-1 text-sm font-medium text-blue-600 transition-colors hover:text-blue-700 dark:text-blue-400 dark:hover:text-blue-300"
                  >
                    <ChevronLeft className="size-4 transition-transform group-hover:-translate-x-0.5" aria-hidden />
                    {breadcrumb.parentLabel}
                  </Link>
                  <span className="text-sm text-muted-foreground/50" aria-hidden>/</span>
                  <h1 className="text-base font-bold tracking-tight text-foreground sm:text-lg" aria-current="page">
                    {breadcrumb.currentLabel}
                  </h1>
                </>
              ) : (
                <h1 className="text-base font-bold tracking-tight text-foreground sm:text-lg" aria-current="page">
                  {breadcrumb.currentLabel}
                </h1>
              )}
            </nav>
          </div>

          {/* Right: Live System Status Pill & User Menu */}
          <div className="flex items-center gap-3">
            {/* Live Operational Status Beacon */}
            <div className="hidden lg:flex items-center gap-2 rounded-full border border-emerald-500/20 bg-emerald-500/10 px-3 py-1 text-xs font-medium text-emerald-600 dark:text-emerald-400 shadow-2xs">
              <span className="relative flex size-2">
                <span className="absolute inline-flex size-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                <span className="relative inline-flex size-2 rounded-full bg-emerald-500" />
              </span>
              <Activity className="size-3.5" />
              <span>{td("liveOperational")}</span>
            </div>

            <div className="h-4 w-px bg-border/60 hidden lg:block" aria-hidden />

            {/* Clean User profile avatar */}
            <UserMenu />
          </div>
        </header>

        {/* Main Content View with Smooth Entry Transition */}
        <m.main
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
          className="flex flex-1 flex-col min-h-0 overflow-y-auto p-4 sm:p-6 lg:p-8 max-w-7xl w-full mx-auto"
        >
          {children}
        </m.main>
      </div>
    </div>
  );
}

