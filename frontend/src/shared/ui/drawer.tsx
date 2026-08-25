"use client";

import {
  useCallback,
  useEffect,
  useId,
  useSyncExternalStore,
  type ComponentType,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import { X } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { m } from "@/shared/lib/motion";

const emptySubscribe = () => () => {};
const useIsMounted = () =>
  useSyncExternalStore(
    emptySubscribe,
    () => true,
    () => false,
  );

export interface DrawerProps {
  /** Rendered next to the title in a small rounded icon badge. */
  icon: ComponentType<{ className?: string }>;
  title: string;
  subtitle?: string;
  onClose: () => void;
  /** aria-label for the header close button. */
  closeLabel: string;
  children: ReactNode;
}

/**
 * Ultra-Premium Slide-over Drawer rendered directly into `document.body` via React Portal.
 * Features Framer Motion slide physics, glassmorphism, and responsive width.
 */
export function Drawer({ icon: Icon, title, subtitle, onClose, closeLabel, children }: DrawerProps) {
  const titleId = useId();
  const isMounted = useIsMounted();

  const handleKeyDown = useCallback(
    (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    },
    [onClose],
  );

  useEffect(() => {
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [handleKeyDown]);

  if (!isMounted) return null;

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex justify-end"
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
    >
      {/* Backdrop overlay */}
      <m.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.2 }}
        className="fixed inset-0 bg-black/65 backdrop-blur-md dark:bg-black/80"
        aria-hidden="true"
        onClick={onClose}
      />

      {/* High-Tech Slide-over Panel */}
      <m.div
        initial={{ x: "100%" }}
        animate={{ x: 0 }}
        exit={{ x: "100%" }}
        transition={{ type: "spring", damping: 28, stiffness: 300 }}
        className="relative z-10 flex h-full w-full max-w-xl flex-col overflow-y-auto rounded-l-3xl border-l border-border/80 bg-card/95 shadow-2xl backdrop-blur-2xl ring-1 ring-black/10 dark:ring-white/10"
      >
        {/* Header */}
        <div className="sticky top-0 z-20 flex items-center justify-between border-b border-border/40 bg-card/90 px-7 sm:px-8 py-5 backdrop-blur-xl">
          <div className="flex items-center gap-3.5 min-w-0">
            <Icon className="size-10 shrink-0 rounded-2xl shadow-xs" aria-hidden="true" />
            <div className="min-w-0">
              <h2 id={titleId} className="text-lg font-bold tracking-tight text-foreground truncate">
                {title}
              </h2>
              {subtitle && (
                <p className="text-xs text-muted-foreground truncate">{subtitle}</p>
              )}
            </div>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={onClose}
            aria-label={closeLabel}
            className="size-9 shrink-0 p-0 rounded-xl text-muted-foreground hover:bg-muted hover:text-foreground cursor-pointer transition-colors"
          >
            <X className="size-4.5" aria-hidden="true" />
          </Button>
        </div>

        {/* Body */}
        <div className="flex flex-1 flex-col px-7 sm:px-8 py-6">{children}</div>
      </m.div>
    </div>,
    document.body,
  );
}
