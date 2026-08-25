"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Menu, ChevronLeft } from "lucide-react";
import { Link, usePathname } from "@/shared/lib/i18n/navigation";
import { ROUTES } from "@/shared/constants/routes";
import { DashboardSidebar } from "./dashboard-sidebar";
import { UserMenu } from "@/modules/auth";

interface DashboardShellProps {
  children: React.ReactNode;
}

interface Breadcrumb {
  currentLabel: string;
  parentLabel?: string;
  parentHref?: string;
}

export function DashboardShell({ children }: DashboardShellProps) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const t = useTranslations("common.nav");
  const tm = useTranslations("common.meta");
  const pathname = usePathname();

  const getBreadcrumb = (): Breadcrumb => {
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
    if (
      pathname.startsWith(ROUTES.adminProjects) &&
      pathname !== ROUTES.adminProjects
    ) {
      return {
        currentLabel: t("detail"),
        parentLabel: t("projects"),
        parentHref: ROUTES.adminProjects,
      };
    }
    if (
      pathname.startsWith(ROUTES.adminIncidents) &&
      pathname !== ROUTES.adminIncidents
    ) {
      return {
        currentLabel: t("detail"),
        parentLabel: t("incidents"),
        parentHref: ROUTES.adminIncidents,
      };
    }

    // Top-level list pages — no back link
    if (pathname.startsWith(ROUTES.adminUsers)) return { currentLabel: t("users") };
    if (pathname.startsWith(ROUTES.adminRoles)) return { currentLabel: t("roles") };
    if (pathname === ROUTES.adminProjects) return { currentLabel: t("projects") };
    if (pathname === ROUTES.adminAuditLog) return { currentLabel: t("auditLog") };
    if (pathname === ROUTES.adminCloudflareAccounts) return { currentLabel: t("cloudflareAccounts") };
    if (pathname === ROUTES.adminIncidents) return { currentLabel: t("incidents") };

    return { currentLabel: t("dashboard") };
  };

  const breadcrumb = getBreadcrumb();

  return (
    <div className="flex min-h-screen w-full bg-slate-50/50 dark:bg-background text-foreground">
      {/* 1. Permanent Desktop Sidebar & Mobile Slide-over Drawer */}
      <DashboardSidebar
        mobileOpen={mobileOpen}
        onMobileClose={() => setMobileOpen(false)}
      />

      {/* 2. Main Area (Header + Content) */}
      <div className="flex min-w-0 flex-1 flex-col">
        {/* Top Navbar: Shadow-based elevation without harsh border lines */}
        <header className="sticky top-0 z-20 flex h-16 items-center justify-between bg-card/80 px-4 shadow-xs backdrop-blur-md sm:px-6 lg:px-8">
          {/* Left: Mobile hamburger & Breadcrumb Title */}
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => setMobileOpen(true)}
              aria-label={t("openMenu")}
              className="flex size-9 items-center justify-center rounded-xl bg-card text-foreground shadow-xs transition-colors hover:bg-muted md:hidden cursor-pointer"
            >
              <Menu className="size-5" />
            </button>

            <nav className="flex items-center gap-1.5" aria-label={t("breadcrumb")}>
              <span className="text-sm font-medium text-muted-foreground hidden sm:inline">
                {tm("appName")} /
              </span>

              {breadcrumb.parentHref ? (
                <>
                  <Link
                    href={breadcrumb.parentHref}
                    className="group flex items-center gap-1 text-sm font-medium text-blue-600 transition-colors hover:text-blue-700 dark:text-blue-400 dark:hover:text-blue-300"
                  >
                    <ChevronLeft className="size-4 transition-transform group-hover:-translate-x-0.5" aria-hidden />
                    {breadcrumb.parentLabel}
                  </Link>
                  <span className="text-sm text-muted-foreground/60" aria-hidden>/</span>
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

          {/* Right: Clean User profile avatar */}
          <div className="flex items-center gap-3">
            <UserMenu />
          </div>
        </header>

        {/* Main Content View */}
        <main className="flex-1 p-6 sm:p-8 max-w-7xl w-full mx-auto">
          {children}
        </main>
      </div>
    </div>
  );
}
