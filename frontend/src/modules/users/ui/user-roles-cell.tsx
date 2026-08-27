"use client";

import { useState, useRef, useEffect } from "react";
import { createPortal } from "react-dom";
import { useTranslations } from "next-intl";
import { Shield, ShieldCheck, Key, X, Layers } from "lucide-react";
import { isProtectedAdminRole } from "@/entities/role";
import { SYSTEM_ROLE_NAMES } from "@/shared/constants/roles";
import { AnimatePresence, m } from "@/shared/lib/motion";
import { useIsMounted } from "@/shared/hooks/use-is-mounted";

interface UserRolesCellProps {
  roles: string[];
  userName?: string;
  onAssignRoles?: () => void;
  canAssign?: boolean;
}

export function UserRolesCell({
  roles,
  userName,
  onAssignRoles,
  canAssign,
}: UserRolesCellProps) {
  const t = useTranslations("users.rolePopover");
  const [isOpen, setIsOpen] = useState(false);
  const [coords, setCoords] = useState<{ top: number; left: number }>({ top: 0, left: 0 });
  const isMounted = useIsMounted();
  const triggerRef = useRef<HTMLButtonElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);

  const displayRoles =
    roles && roles.length > 0 ? roles : [SYSTEM_ROLE_NAMES.MEMBER];
  const primaryRole = displayRoles[0];
  const remainingRoles = displayRoles.slice(1);
  const hasMore = remainingRoles.length > 0;

  const handleToggle = () => {
    if (!isOpen && triggerRef.current) {
      const rect = triggerRef.current.getBoundingClientRect();
      const popoverWidth = 280;
      const left = Math.max(
        16,
        Math.min(window.innerWidth - popoverWidth - 16, rect.left)
      );
      setCoords({
        top: rect.bottom + 6,
        left,
      });
    }
    setIsOpen(!isOpen);
  };

  // Handle click outside to close popover
  useEffect(() => {
    if (!isOpen) return;

    const handleClickOutside = (event: MouseEvent) => {
      const target = event.target as Node;
      if (
        popoverRef.current &&
        !popoverRef.current.contains(target) &&
        triggerRef.current &&
        !triggerRef.current.contains(target)
      ) {
        setIsOpen(false);
      }
    };

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setIsOpen(false);
      }
    };

    const handleScroll = () => {
      if (isOpen && triggerRef.current) {
        const rect = triggerRef.current.getBoundingClientRect();
        const popoverWidth = 280;
        const left = Math.max(
          16,
          Math.min(window.innerWidth - popoverWidth - 16, rect.left)
        );
        setCoords({
          top: rect.bottom + 6,
          left,
        });
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleKeyDown);
    window.addEventListener("scroll", handleScroll, true);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleKeyDown);
      window.removeEventListener("scroll", handleScroll, true);
    };
  }, [isOpen]);

  const getRoleStyle = (roleName: string) => {
    if (isProtectedAdminRole(roleName)) {
      return {
        badge:
          "border-amber-500/40 bg-amber-500/15 text-amber-700 dark:text-amber-300 shadow-2xs",
        icon: <Key className="size-3 text-amber-500" />,
      };
    }
    if (roleName.toUpperCase() === SYSTEM_ROLE_NAMES.MEMBER.toUpperCase()) {
      return {
        badge:
          "border-blue-500/30 bg-blue-500/10 text-blue-600 dark:text-blue-400 shadow-2xs",
        icon: <Shield className="size-3 text-blue-500" />,
      };
    }
    return {
      badge:
        "border-indigo-500/30 bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 shadow-2xs",
      icon: <ShieldCheck className="size-3 text-indigo-500" />,
    };
  };

  const primaryStyle = getRoleStyle(primaryRole);

  return (
    <div className="inline-flex items-center gap-1.5">
      {/* 1. Primary Role Badge */}
      <span
        className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-lg border px-2.5 py-1 text-xs font-semibold uppercase tracking-wider ${primaryStyle.badge}`}
      >
        {primaryStyle.icon}
        {primaryRole}
      </span>

      {/* 2. "+N" Animated Trigger Button */}
      {hasMore && (
        <button
          ref={triggerRef}
          type="button"
          onClick={handleToggle}
          aria-expanded={isOpen}
          aria-label={t("more", { count: remainingRoles.length })}
          className={`group relative inline-flex items-center gap-1 rounded-lg border px-2 py-1 text-xs font-mono font-bold transition-all duration-200 cursor-pointer ${
            isOpen
              ? "border-primary bg-primary text-primary-foreground shadow-xs scale-105"
              : "border-border/80 bg-muted/60 text-muted-foreground hover:border-primary/40 hover:bg-primary/10 hover:text-primary"
          }`}
        >
          <span className="text-[11px]">+{remainingRoles.length}</span>
          <Layers className="size-3 opacity-70 group-hover:opacity-100" />
        </button>
      )}

      {/* 3. High-Tech Glassmorphic Portal Popover (Never clipped by table overflow) */}
      {isMounted &&
        createPortal(
          <AnimatePresence>
            {isOpen && (
              <m.div
                ref={popoverRef}
                initial={{ opacity: 0, scale: 0.92, y: -4 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.95, y: -4 }}
                transition={{ type: "spring", damping: 25, stiffness: 350 }}
                style={{
                  position: "fixed",
                  top: `${coords.top}px`,
                  left: `${coords.left}px`,
                  zIndex: 9999,
                }}
                className="w-[280px] rounded-2xl border border-border/80 bg-card/95 p-3.5 shadow-2xl backdrop-blur-2xl ring-1 ring-black/10 dark:ring-white/10"
              >
                {/* Popover Header */}
                <div className="flex items-center justify-between border-b border-border/40 pb-2.5">
                  <div className="flex items-center gap-2">
                    <div className="flex size-6 items-center justify-center rounded-lg bg-primary/10 text-primary">
                      <Shield className="size-3.5" />
                    </div>
                    <div className="flex flex-col">
                      <span className="text-xs font-bold text-foreground">
                        {t("title")}
                      </span>
                      {userName && (
                        <span className="text-[10px] text-muted-foreground truncate max-w-[150px]">
                          {userName}
                        </span>
                      )}
                    </div>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <span className="inline-flex items-center rounded-full bg-primary/15 px-2 py-0.5 font-mono text-[10px] font-bold text-primary">
                      {displayRoles.length}
                    </span>
                    <button
                      type="button"
                      onClick={() => setIsOpen(false)}
                      className="rounded-md p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground cursor-pointer"
                      aria-label={t("close")}
                    >
                      <X className="size-3.5" />
                    </button>
                  </div>
                </div>

                {/* Popover Roles List */}
                <div className="flex flex-col gap-1.5 py-2.5 max-h-48 overflow-y-auto pr-1">
                  {displayRoles.map((roleName, index) => {
                    const style = getRoleStyle(roleName);
                    return (
                      <m.div
                        key={roleName}
                        initial={{ opacity: 0, x: -6 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: index * 0.04 }}
                        className="flex items-center justify-between rounded-xl border border-border/50 bg-background/80 px-2.5 py-2 transition-colors hover:border-primary/30 hover:bg-muted/40 shadow-2xs"
                      >
                        <div className="flex items-center gap-2">
                          {style.icon}
                          <span className="text-xs font-semibold text-foreground uppercase tracking-wide">
                            {roleName}
                          </span>
                        </div>
                        {index === 0 && (
                          <span className="text-[10px] font-mono text-muted-foreground uppercase">
                            Primary
                          </span>
                        )}
                      </m.div>
                    );
                  })}
                </div>

                {/* Popover Action Footer */}
                {canAssign && onAssignRoles && (
                  <div className="border-t border-border/40 pt-2">
                    <button
                      type="button"
                      onClick={() => {
                        setIsOpen(false);
                        onAssignRoles();
                      }}
                      className="w-full rounded-xl bg-primary/10 py-1.5 text-center text-xs font-semibold text-primary transition-colors hover:bg-primary hover:text-primary-foreground shadow-2xs cursor-pointer"
                    >
                      {t("manageRoles")}
                    </button>
                  </div>
                )}
              </m.div>
            )}
          </AnimatePresence>,
          document.body
        )}
    </div>
  );
}
