"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { LayoutDashboard, Users, Shield, Menu, X } from "lucide-react";
import { Link, usePathname } from "@/shared/lib/i18n/navigation";
import { ROUTES } from "@/shared/constants/routes";
import { Can } from "@/entities/permission";
import { UserMenu } from "@/modules/auth";
import { LanguageSwitch } from "@/modules/auth/ui/language-switch";
import { AnimatePresence, m } from "@/shared/lib/motion";

export function DashboardHeader() {
  const t = useTranslations("common.nav");
  const tm = useTranslations("common.meta");
  const pathname = usePathname();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const isDashboardActive = pathname === ROUTES.dashboard;
  const isUsersActive = pathname === ROUTES.adminUsers;
  const isRolesActive = pathname === ROUTES.adminRoles;

  const closeMobileMenu = () => setMobileMenuOpen(false);

  return (
    <header className="sticky top-0 z-30 w-full border-b border-border/80 bg-background/95 shadow-xs backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
        {/* Left: Brand & Desktop Nav */}
        <div className="flex items-center gap-6 lg:gap-8">
          {/* Brand Logo */}
          <Link
            href={ROUTES.dashboard}
            onClick={closeMobileMenu}
            className="flex items-center gap-2.5 transition-opacity hover:opacity-90"
          >
            <div className="flex size-9 items-center justify-center rounded-xl bg-blue-600 text-white font-extrabold text-base shadow-sm shadow-blue-500/25">
              W
            </div>
            <div className="flex items-center gap-1.5">
              <span className="text-lg font-bold tracking-tight text-foreground">
                {tm("appName")}
              </span>
              <span className="rounded-md border border-blue-200/80 bg-blue-50/80 px-1.5 py-0.5 text-[10px] font-bold tracking-wider text-blue-700 uppercase dark:border-blue-900/60 dark:bg-blue-950/60 dark:text-blue-300">
                ITSM
              </span>
            </div>
          </Link>

          {/* Desktop Navigation Links */}
          <nav className="hidden items-center gap-1.5 md:flex" aria-label="Main Navigation">
            <Link
              href={ROUTES.dashboard}
              className={`flex items-center gap-2 rounded-lg px-3.5 py-2 text-sm font-medium transition-all ${
                isDashboardActive
                  ? "bg-blue-50 text-blue-600 dark:bg-blue-950/60 dark:text-blue-400 font-semibold shadow-xs"
                  : "text-muted-foreground hover:bg-muted/60 hover:text-foreground"
              }`}
            >
              <LayoutDashboard className="size-4" />
              {t("dashboard")}
            </Link>

            <Can I="read" a="user">
              <Link
                href={ROUTES.adminUsers}
                className={`flex items-center gap-2 rounded-lg px-3.5 py-2 text-sm font-medium transition-all ${
                  isUsersActive
                    ? "bg-blue-50 text-blue-600 dark:bg-blue-950/60 dark:text-blue-400 font-semibold shadow-xs"
                    : "text-muted-foreground hover:bg-muted/60 hover:text-foreground"
                }`}
              >
                <Users className="size-4" />
                {t("users")}
              </Link>
            </Can>

            <Can I="read" a="role">
              <Link
                href={ROUTES.adminRoles}
                className={`flex items-center gap-2 rounded-lg px-3.5 py-2 text-sm font-medium transition-all ${
                  isRolesActive
                    ? "bg-blue-50 text-blue-600 dark:bg-blue-950/60 dark:text-blue-400 font-semibold shadow-xs"
                    : "text-muted-foreground hover:bg-muted/60 hover:text-foreground"
                }`}
              >
                <Shield className="size-4" />
                {t("roles")}
              </Link>
            </Can>
          </nav>
        </div>

        {/* Right: Language switch + User menu + Mobile hamburger */}
        <div className="flex items-center gap-2.5 sm:gap-3">
          <div className="hidden sm:block">
            <LanguageSwitch />
          </div>
          <div className="hidden h-5 w-px bg-border sm:block" />
          <UserMenu />

          {/* Mobile hamburger toggle button */}
          <button
            type="button"
            onClick={() => setMobileMenuOpen((prev) => !prev)}
            aria-label="Toggle navigation menu"
            aria-expanded={mobileMenuOpen}
            className="flex size-10 items-center justify-center rounded-lg border border-border bg-background text-foreground transition-colors hover:bg-muted md:hidden"
          >
            {mobileMenuOpen ? (
              <X className="size-5" aria-hidden />
            ) : (
              <Menu className="size-5" aria-hidden />
            )}
          </button>
        </div>
      </div>

      {/* Mobile / Tablet Drawer Menu */}
      <AnimatePresence>
        {mobileMenuOpen && (
          <m.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.2, ease: "easeOut" }}
            className="overflow-hidden border-t border-border/60 bg-background px-4 py-3 md:hidden"
          >
            <nav className="flex flex-col gap-1.5" aria-label="Mobile Navigation">
              <Link
                href={ROUTES.dashboard}
                onClick={closeMobileMenu}
                className={`flex min-h-[44px] items-center gap-3 rounded-lg px-3.5 py-2.5 text-sm font-medium transition-colors ${
                  isDashboardActive
                    ? "bg-blue-50 text-blue-600 dark:bg-blue-950/60 dark:text-blue-400 font-semibold"
                    : "text-muted-foreground hover:bg-muted hover:text-foreground"
                }`}
              >
                <LayoutDashboard className="size-4 shrink-0" />
                {t("dashboard")}
              </Link>

              <Can I="read" a="user">
                <Link
                  href={ROUTES.adminUsers}
                  onClick={closeMobileMenu}
                  className={`flex min-h-[44px] items-center gap-3 rounded-lg px-3.5 py-2.5 text-sm font-medium transition-colors ${
                    isUsersActive
                      ? "bg-blue-50 text-blue-600 dark:bg-blue-950/60 dark:text-blue-400 font-semibold"
                      : "text-muted-foreground hover:bg-muted hover:text-foreground"
                  }`}
                >
                  <Users className="size-4 shrink-0" />
                  {t("users")}
                </Link>
              </Can>

              <Can I="read" a="role">
                <Link
                  href={ROUTES.adminRoles}
                  onClick={closeMobileMenu}
                  className={`flex min-h-[44px] items-center gap-3 rounded-lg px-3.5 py-2.5 text-sm font-medium transition-colors ${
                    isRolesActive
                      ? "bg-blue-50 text-blue-600 dark:bg-blue-950/60 dark:text-blue-400 font-semibold"
                      : "text-muted-foreground hover:bg-muted hover:text-foreground"
                  }`}
                >
                  <Shield className="size-4 shrink-0" />
                  {t("roles")}
                </Link>
              </Can>
            </nav>

            <div className="mt-3 flex items-center justify-between border-t border-border/60 pt-3 sm:hidden">
              <span className="text-xs text-muted-foreground">Ngôn ngữ / Language:</span>
              <LanguageSwitch />
            </div>
          </m.div>
        )}
      </AnimatePresence>
    </header>
  );
}
