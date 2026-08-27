"use client";

import { useState, useRef, useEffect } from "react";
import { createPortal } from "react-dom";
import { useTranslations } from "next-intl";
import { Shield, Key, X } from "lucide-react";
import type { PermissionItem } from "@/entities/role";
import { AnimatePresence, m } from "@/shared/lib/motion";
import { useIsMounted } from "@/shared/hooks/use-is-mounted";

interface RolePermissionsCellProps {
  permissions: PermissionItem[];
  roleName: string;
  isSystem?: boolean;
}

export function RolePermissionsCell({
  permissions,
  roleName,
}: RolePermissionsCellProps) {
  const t = useTranslations("roles");
  const tp = useTranslations("roles.permissionsPopover");
  const [isOpen, setIsOpen] = useState(false);
  const [coords, setCoords] = useState<{ top: number; left: number }>({ top: 0, left: 0 });
  const isMounted = useIsMounted();
  const triggerRef = useRef<HTMLButtonElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);

  const count = permissions.length;

  const handleToggle = () => {
    if (!isOpen && triggerRef.current) {
      const rect = triggerRef.current.getBoundingClientRect();
      const popoverWidth = 300;
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
        const popoverWidth = 300;
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

  return (
    <div className="inline-flex items-center">
      {/* Clickable Pill Trigger */}
      <button
        ref={triggerRef}
        type="button"
        onClick={handleToggle}
        aria-expanded={isOpen}
        className={`group inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs font-mono font-bold transition-all duration-200 cursor-pointer ${
          isOpen
            ? "border-primary bg-primary text-primary-foreground shadow-xs scale-105"
            : "border-border/70 bg-muted/60 text-foreground hover:border-primary/40 hover:bg-primary/10 hover:text-primary"
        }`}
      >
        <Key className="size-3 opacity-70 group-hover:opacity-100" />
        <span>{t("permissionsCount", { count })}</span>
      </button>

      {/* High-Tech Animated Portal Popover (Never clipped by table overflow) */}
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
                className="w-[300px] rounded-2xl border border-border/80 bg-card/95 p-3.5 shadow-2xl backdrop-blur-2xl ring-1 ring-black/10 dark:ring-white/10"
              >
                {/* Popover Header */}
                <div className="flex items-center justify-between border-b border-border/40 pb-2.5">
                  <div className="flex items-center gap-2">
                    <div className="flex size-6 items-center justify-center rounded-lg bg-primary/10 text-primary">
                      <Shield className="size-3.5" />
                    </div>
                    <div className="flex flex-col">
                      <span className="text-xs font-bold text-foreground">
                        {tp("title")}
                      </span>
                      <span className="text-[10px] text-muted-foreground truncate max-w-[170px]">
                        {roleName}
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <span className="inline-flex items-center rounded-full bg-primary/15 px-2 py-0.5 font-mono text-[10px] font-bold text-primary">
                      {count}
                    </span>
                    <button
                      type="button"
                      onClick={() => setIsOpen(false)}
                      className="rounded-md p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground cursor-pointer"
                      aria-label={tp("close")}
                    >
                      <X className="size-3.5" />
                    </button>
                  </div>
                </div>

                {/* Popover Permissions List */}
                <div className="flex flex-col gap-1.5 py-2.5 max-h-56 overflow-y-auto pr-1">
                  {count === 0 ? (
                    <p className="py-4 text-center text-xs text-muted-foreground">
                      {t("empty")}
                    </p>
                  ) : (
                    permissions.map((perm, index) => (
                      <m.div
                        key={perm.id || `${perm.resource}:${perm.action}`}
                        initial={{ opacity: 0, x: -6 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: index * 0.02 }}
                        className="flex items-center justify-between rounded-xl border border-border/50 bg-background/80 px-2.5 py-1.5 text-xs font-mono transition-colors hover:border-primary/30 hover:bg-muted/40 shadow-2xs"
                      >
                        <span className="font-semibold text-foreground">
                          {perm.resource}
                        </span>
                        <span className="rounded-md border border-primary/20 bg-primary/10 px-1.5 py-0.5 text-[10px] font-bold uppercase text-primary">
                          {perm.action}
                        </span>
                      </m.div>
                    ))
                  )}
                </div>
              </m.div>
            )}
          </AnimatePresence>,
          document.body
        )}
    </div>
  );
}
