"use client";

import { useCallback, useEffect, useId, type ComponentType, type ReactNode } from "react";
import { AlertCircle, X } from "lucide-react";
import { Button } from "@/shared/ui/button";

const DIALOG_SIZES = {
  sm: "max-w-sm",
  md: "max-w-md",
  lg: "max-w-xl",
  xl: "max-w-2xl",
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
 * Shared modal shell for form dialogs — overlay, centering, ARIA wiring
 * (role="dialog", aria-modal, aria-labelledby), header (icon + title +
 * close button), Escape and click-outside-to-close. Mirrors the existing
 * `ConfirmDialog` primitive's visual language (rounded-2xl, shadow-2xl,
 * backdrop-blur) so every modal in the app looks and behaves the same way.
 *
 * Callers render their own form/body as children — this component only
 * owns the shell and header, never form fields or submit logic.
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

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-xs animate-in fade-in-0"
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
    >
      <div
        className="fixed inset-0"
        aria-hidden="true"
        onClick={() => !disableClose && onClose()}
      />

      <div
        className={`relative flex max-h-[90vh] w-full ${DIALOG_SIZES[size]} flex-col rounded-2xl border bg-card shadow-2xl animate-in zoom-in-95`}
      >
        <div className="flex items-center justify-between border-b px-6 py-4">
          <div className="flex items-center gap-2.5">
            <div className="flex size-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <Icon className="size-4" aria-hidden="true" />
            </div>
            <h2 id={titleId} className="text-lg font-bold text-foreground">
              {title}
            </h2>
          </div>
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={onClose}
            disabled={disableClose}
            aria-label={closeLabel}
          >
            <X className="size-4" aria-hidden="true" />
          </Button>
        </div>

        {children}
      </div>
    </div>
  );
}

/** Uniform error banner for inside a Dialog's form body. */
export function DialogErrorAlert({ message }: { message: string }) {
  return (
    <div
      role="alert"
      className="flex items-center gap-2 rounded-lg border border-destructive/20 bg-destructive/10 p-3 text-sm text-destructive"
    >
      <AlertCircle className="size-4 shrink-0" aria-hidden="true" />
      <span>{message}</span>
    </div>
  );
}
