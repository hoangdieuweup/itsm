"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Menu } from "lucide-react";
import { usePathname } from "@/shared/lib/i18n/navigation";
import { ROUTES } from "@/shared/constants/routes";
import { DashboardSidebar } from "./dashboard-sidebar";
import { UserMenu } from "@/modules/auth";

interface DashboardShellProps {
  children: React.ReactNode;
}

export function DashboardShell({ children }: DashboardShellProps) {
  const [mobileOpen, setMobileOpen] = useState(false);
  const t = useTranslations("common.nav");
  const pathname = usePathname();

  const getPageTitle = () => {
    if (pathname === ROUTES.adminUsers) return t("users");
    if (pathname === ROUTES.adminRoles) return t("roles");
    return t("dashboard");
  };

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

            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-muted-foreground hidden sm:inline">
                ITSM /
              </span>
              <h1 className="text-base font-bold tracking-tight text-foreground sm:text-lg">
                {getPageTitle()}
              </h1>
            </div>
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
