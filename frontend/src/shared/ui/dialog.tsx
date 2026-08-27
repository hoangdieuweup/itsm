"use client";

import {
  useCallback,
  useEffect,
  useId,
  type ComponentType,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import { AlertCircle, X } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { m } from "@/shared/lib/motion";
import { useIsMounted } from "@/shared/hooks/use-is-mounted";

const DIALOG_SIZES = {
  sm: "max-w-sm",
  md: "max-w-md",
  lg: "max-w-xl",
  xl: "max-w-2xl",
  "2xl": "max-w-3xl",
} as const;

export type DialogSize = keyof typeof DIALOG_SIZES;

export interface DialogProps {
  /** Rendered next to the title in a small rounded icon badge. */
  icon: ComponentType<{ className?: string }>;
  title: string;
  onClose: () => void;
  /** aria-label for the header close button. */
  closeLabel: string;
  size?: DialogSize;
  /** Disables both the header close button and Escape/click-outside-to-close — for mid-submit states. */
  disableClose?: boolean;
  children: ReactNode;
}

/**
 * Clean & Modern Seamless Modal Shell rendered directly into `document.body` via React Portal.
 * Floating card design with spacious, breathable padding and seamless typography.
 */
export function Dialog({
  icon: Icon,
  title,
  onClose,
  closeLabel,
  size = "md",
  disableClose = false,
  children,
}: DialogProps) {
  const titleId = useId();
  const isMounted = useIsMounted();

  const handleKeyDown = useCallback(
    (event: KeyboardEvent) => {
      if (event.key === "Escape" && !disableClose) onClose();
    },
    [onClose, disableClose],
  );

  useEffect(() => {
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [handleKeyDown]);

  if (!isMounted) return null;

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6"
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
    >
      {/* Backdrop overlay with smooth blur */}
      <m.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.2 }}
        className="fixed inset-0 bg-black/50 backdrop-blur-sm dark:bg-black/80"
        aria-hidden="true"
        onClick={() => !disableClose && onClose()}
      />

      {/* Clean Floating Modal Container - Strictly capped at 85vh */}
      <m.div
        initial={{ opacity: 0, scale: 0.95, y: 10 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 10 }}
        transition={{ type: "spring", damping: 28, stiffness: 340 }}
        className={`relative z-10 flex max-h-[85vh] min-h-0 w-full ${DIALOG_SIZES[size]} flex-col overflow-hidden rounded-3xl border border-border/40 bg-card/95 shadow-2xl backdrop-blur-2xl`}
      >
        {/* Spacious Seamless Header with generous padding */}
        <div className="flex shrink-0 items-center justify-between border-b border-border/30 px-6 sm:px-8 py-4 sm:py-5">
          <div className="flex items-center gap-3.5 min-w-0">
            <Icon className="size-9 sm:size-10 shrink-0 rounded-2xl shadow-xs" aria-hidden="true" />
            <h2 id={titleId} className="text-lg sm:text-xl font-bold tracking-tight text-foreground truncate">
              {title}
            </h2>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={onClose}
            disabled={disableClose}
            aria-label={closeLabel}
            className="size-9 shrink-0 p-0 rounded-xl text-muted-foreground hover:bg-muted/80 hover:text-foreground cursor-pointer transition-colors"
          >
            <X className="size-4.5" aria-hidden="true" />
          </Button>
        </div>

        {/* Modal Content */}
        {children}
      </m.div>
    </div>,
    document.body,
  );
}

/** Uniform error banner for inside a Dialog's form body. */
export function DialogErrorAlert({ message }: { message: string }) {
  return (
    <div
      role="alert"
      className="flex items-center gap-2.5 rounded-2xl border border-destructive/20 bg-destructive/10 p-4 text-sm text-destructive shadow-2xs"
    >
      <AlertCircle className="size-4.5 shrink-0" aria-hidden="true" />
      <span className="font-medium">{message}</span>
    </div>
  );
}
