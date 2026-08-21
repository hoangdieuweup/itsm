"use client";

import { useSyncExternalStore } from "react";
import { useTranslations } from "next-intl";
import {
  LayoutDashboard,
  Users,
  Shield,
  ChevronLeft,
  ChevronRight,
  LogOut,
  X,
  type LucideIcon,
} from "lucide-react";
import { Link, usePathname } from "@/shared/lib/i18n/navigation";
import { ROUTES } from "@/shared/constants/routes";
import { Can } from "@/entities/permission";
import { LanguageSwitch } from "@/modules/auth/ui/language-switch";
import { useAuthSession } from "@/modules/auth/hooks/use-auth-session";
import { useLogout } from "@/modules/auth/hooks/use-logout";
import { Avatar, AvatarFallback } from "@/shared/ui/avatar";
import { AnimatePresence, m } from "@/shared/lib/motion";
import { cn } from "@/shared/lib/utils";

interface DashboardSidebarProps {
  mobileOpen: boolean;
  onMobileClose: () => void;
}

interface NavItem {
  href: string;
  label: string;
  icon: LucideIcon;
  active: boolean;
  permission: { action: string; resource: string } | null;
}

const SIDEBAR_STORAGE_KEY = "itsm_sidebar_collapsed";

const sidebarStore = {
  getSnapshot: () => {
    try {
      if (typeof window === "undefined") return false;
      return localStorage.getItem(SIDEBAR_STORAGE_KEY) === "true";
    } catch {
      return false;
    }
  },
  getServerSnapshot: () => false,
  subscribe: (callback: () => void) => {
    if (typeof window === "undefined") return () => {};
    window.addEventListener("sidebar-toggle", callback);
    window.addEventListener("storage", callback);
    return () => {
      window.removeEventListener("sidebar-toggle", callback);
      window.removeEventListener("storage", callback);
    };
  },
  toggle: (current: boolean) => {
    try {
      localStorage.setItem(SIDEBAR_STORAGE_KEY, String(!current));
      window.dispatchEvent(new Event("sidebar-toggle"));
    } catch {}
  },
};

function getInitials(name?: string | null): string {
  if (!name) return "U";
  return (
    name
      .trim()
      .split(/\s+/)
      .map((p) => p[0] || "")
      .join("")
      .slice(0, 2)
      .toUpperCase() || "U"
  );
}

function SidebarBrand({
  appName,
  appDescription,
  isCollapsed,
  onToggleCollapse,
  collapseLabel,
}: {
  appName: string;
  appDescription: string;
  isCollapsed: boolean;
  onToggleCollapse: () => void;
  collapseLabel: string;
}) {
  return (
    <div className="flex h-16 items-center justify-between px-4">
      <Link
        href={ROUTES.dashboard}
        className="flex items-center gap-3 overflow-hidden transition-opacity hover:opacity-90"
        title={appName}
      >
        <div className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-blue-600 to-indigo-600 text-white font-black text-base shadow-sm shadow-blue-500/25">
          W
        </div>
        {!isCollapsed && (
          <div className="flex flex-col overflow-hidden whitespace-nowrap">
            <div className="flex items-center gap-1.5">
              <span className="text-base font-bold tracking-tight text-foreground">
                {appName}
              </span>
              <span className="rounded-md bg-blue-50 px-1.5 py-0.5 text-[10px] font-bold tracking-wider text-blue-700 uppercase dark:bg-blue-950/80 dark:text-blue-300">
                Console
              </span>
            </div>
            <span className="text-[11px] text-muted-foreground truncate">
              {appDescription}
            </span>
          </div>
        )}
      </Link>

      {!isCollapsed && (
        <button
          type="button"
          onClick={onToggleCollapse}
          aria-label={collapseLabel}
          className="flex size-8 shrink-0 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-muted hover:text-foreground cursor-pointer"
          title={collapseLabel}
        >
          <ChevronLeft className="size-4" />
        </button>
      )}
    </div>
  );
}

function SidebarNavList({
  items,
  isCollapsed,
  mainMenuLabel,
  onItemClick,
}: {
  items: NavItem[];
  isCollapsed?: boolean;
  mainMenuLabel: string;
  onItemClick?: () => void;
}) {
  return (
    <div className="flex-1 space-y-4 overflow-y-auto px-3 py-2">
      <div>
        {!isCollapsed && (
          <div className="px-3 pb-2 text-[11px] font-bold uppercase tracking-wider text-muted-foreground/60">
            {mainMenuLabel}
          </div>
        )}
        <nav className="space-y-1" aria-label="Main Navigation">
          {items.map((item) => {
            const Icon = item.icon;
            const linkContent = (
              <Link
                key={item.href}
                href={item.href}
                onClick={onItemClick}
                title={isCollapsed ? item.label : undefined}
                className={cn(
                  "group relative flex items-center gap-3 rounded-xl px-3.5 py-2.5 text-sm font-medium transition-all",
                  item.active
                    ? "bg-blue-50/90 text-blue-600 dark:bg-blue-950/60 dark:text-blue-400 font-semibold shadow-2xs"
                    : "text-muted-foreground hover:bg-muted/70 hover:text-foreground",
                  isCollapsed && "justify-center px-0 h-11"
                )}
              >
                {item.active && (
                  <span className="absolute left-0 top-1/2 h-5 w-1 -translate-y-1/2 rounded-r-full bg-blue-600 dark:bg-blue-400" />
                )}
                <Icon
                  className={cn(
                    "size-5 shrink-0 transition-transform group-hover:scale-105",
                    item.active
                      ? "text-blue-600 dark:text-blue-400"
                      : "text-muted-foreground group-hover:text-foreground"
                  )}
                  aria-hidden
                />
                {!isCollapsed && <span className="truncate">{item.label}</span>}
              </Link>
            );

            if (item.permission) {
              return (
                <Can
                  key={item.href}
                  I={item.permission.action}
                  a={item.permission.resource}
                >
                  {linkContent}
                </Can>
              );
            }

            return linkContent;
          })}
        </nav>
      </div>
    </div>
  );
}

function SidebarUserProfile({
  name,
  roleName,
  initials,
  logoutLabel,
  onLogout,
  isPending,
}: {
  name: string;
  roleName: string;
  initials: string;
  logoutLabel: string;
  onLogout: () => void;
  isPending: boolean;
}) {
  return (
    <div className="flex items-center justify-between rounded-2xl bg-muted/40 p-2.5 shadow-2xs">
      <div className="flex items-center gap-2.5 overflow-hidden">
        <Avatar className="size-8 shrink-0">
          <AvatarFallback className="bg-blue-600/10 text-blue-600 text-xs font-bold dark:bg-blue-400/10 dark:text-blue-400">
            {initials}
          </AvatarFallback>
        </Avatar>
        <div className="flex flex-col overflow-hidden">
          <span className="text-xs font-semibold text-foreground truncate leading-tight">
            {name}
          </span>
          <span className="text-[10px] text-muted-foreground capitalize truncate leading-tight mt-0.5">
            {roleName}
          </span>
        </div>
      </div>

      <button
        type="button"
        onClick={onLogout}
        disabled={isPending}
        aria-label={logoutLabel}
        className="flex size-7 shrink-0 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-rose-50 hover:text-rose-600 dark:hover:bg-rose-950/50 cursor-pointer"
        title={logoutLabel}
      >
        <LogOut className="size-3.5" />
      </button>
    </div>
  );
}

export function DashboardSidebar({
  mobileOpen,
  onMobileClose,
}: DashboardSidebarProps) {
  const t = useTranslations("common.nav");
  const tm = useTranslations("common.meta");
  const tu = useTranslations("auth.userMenu");
  const pathname = usePathname();
  const { data: session } = useAuthSession();
  const logout = useLogout();

  const isCollapsed = useSyncExternalStore(
    sidebarStore.subscribe,
    sidebarStore.getSnapshot,
    sidebarStore.getServerSnapshot
  );

  const navItems: NavItem[] = [
    {
      href: ROUTES.dashboard,
      label: t("dashboard"),
      icon: LayoutDashboard,
      active: pathname === ROUTES.dashboard,
      permission: null,
    },
    {
      href: ROUTES.adminUsers,
      label: t("users"),
      icon: Users,
      active: pathname === ROUTES.adminUsers,
      permission: { action: "read", resource: "user" },
    },
    {
      href: ROUTES.adminRoles,
      label: t("roles"),
      icon: Shield,
      active: pathname === ROUTES.adminRoles,
      permission: { action: "read", resource: "role" },
    },
  ];

  const initials = getInitials(session?.user?.name);
  const userName = session?.user?.name || "";
  const roleName = session?.roleName || "User";

  return (
    <>
      {/* 1. Desktop Permanent Sidebar */}
      <aside
        aria-label="Sidebar"
        className={cn(
          "sticky top-0 max-md:hidden flex h-screen shrink-0 flex-col bg-card shadow-xs transition-[width] duration-300 ease-in-out z-30",
          isCollapsed ? "w-[72px]" : "w-64"
        )}
      >
        <SidebarBrand
          appName={tm("appName")}
          appDescription={tm("appDescription")}
          isCollapsed={isCollapsed}
          onToggleCollapse={() => sidebarStore.toggle(isCollapsed)}
          collapseLabel={t("collapseSidebar")}
        />

        <SidebarNavList
          items={navItems}
          isCollapsed={isCollapsed}
          mainMenuLabel={t("mainMenu")}
        />

        <div className="flex flex-col gap-2.5 p-3">
          {isCollapsed ? (
            <div className="flex justify-center pb-2">
              <button
                type="button"
                onClick={() => sidebarStore.toggle(isCollapsed)}
                aria-label={t("expandSidebar")}
                className="flex size-9 items-center justify-center rounded-xl bg-muted/40 text-muted-foreground shadow-2xs transition-colors hover:bg-muted hover:text-foreground cursor-pointer"
                title={t("expandSidebar")}
              >
                <ChevronRight className="size-4" />
              </button>
            </div>
          ) : (
            <>
              <div className="flex items-center justify-between px-2">
                <span className="text-xs font-medium text-muted-foreground">
                  {t("language")}
                </span>
                <LanguageSwitch />
              </div>

              {session?.user && (
                <SidebarUserProfile
                  name={userName}
                  roleName={roleName}
                  initials={initials}
                  logoutLabel={tu("logout")}
                  onLogout={() => logout.mutate()}
                  isPending={logout.isPending}
                />
              )}
            </>
          )}
        </div>
      </aside>

      {/* 2. Mobile Slide-over Drawer */}
      <AnimatePresence>
        {mobileOpen && (
          <div
            className="fixed inset-0 z-50 md:hidden"
            role="dialog"
            aria-modal="true"
          >
            <m.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.2 }}
              onClick={onMobileClose}
              className="fixed inset-0 bg-black/50 backdrop-blur-xs"
            />

            <m.aside
              initial={{ x: "-100%" }}
              animate={{ x: 0 }}
              exit={{ x: "-100%" }}
              transition={{ type: "spring", damping: 25, stiffness: 260 }}
              className="fixed inset-y-0 left-0 z-10 flex w-72 max-w-[80vw] flex-col rounded-r-2xl bg-card shadow-2xl"
            >
              <div className="flex h-16 items-center justify-between px-4">
                <div className="flex items-center gap-2.5">
                  <div className="flex size-9 items-center justify-center rounded-xl bg-gradient-to-br from-blue-600 to-indigo-600 text-white font-black text-base shadow-sm shadow-blue-500/25">
                    W
                  </div>
                  <div className="flex flex-col">
                    <span className="text-base font-bold tracking-tight text-foreground">
                      {tm("appName")}
                    </span>
                    <span className="text-[11px] text-muted-foreground">
                      ITSM Console
                    </span>
                  </div>
                </div>

                <button
                  type="button"
                  onClick={onMobileClose}
                  aria-label={t("closeMenu")}
                  className="flex size-8 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-muted hover:text-foreground cursor-pointer"
                >
                  <X className="size-5" />
                </button>
              </div>

              <SidebarNavList
                items={navItems}
                mainMenuLabel={t("mainMenu")}
                onItemClick={onMobileClose}
              />

              <div className="flex flex-col gap-3 p-4">
                <div className="flex items-center justify-between px-1">
                  <span className="text-xs font-medium text-muted-foreground">
                    {t("language")}
                  </span>
                  <LanguageSwitch />
                </div>

                {session?.user && (
                  <SidebarUserProfile
                    name={userName}
                    roleName={roleName}
                    initials={initials}
                    logoutLabel={tu("logout")}
                    onLogout={() => logout.mutate()}
                    isPending={logout.isPending}
                  />
                )}
              </div>
            </m.aside>
          </div>
        )}
      </AnimatePresence>
    </>
  );
}
