"use client";

import { useCallback, useEffect, useId, type ComponentType, type ReactNode } from "react";
import { X } from "lucide-react";
import { Button } from "@/shared/ui/button";

export interface DrawerProps {
  /** Rendered next to the title in a small rounded icon badge. */
  icon: ComponentType<{ className?: string }>;
  title: string;
  onClose: () => void;
  /** aria-label for the header close button. */
  closeLabel: string;
  children: ReactNode;
}

/**
 * Shared right-anchored slide-in panel — overlay, ARIA wiring (role="dialog",
 * aria-modal, aria-labelledby), header (icon + title + close button), Escape
 * and click-outside-to-close. Mirrors `Dialog`'s exact shell/behavior (also
 * hand-rolled, not built on a headless-UI primitive) so every overlay in the
 * app behaves the same way; only the position/motion differ — anchored to
 * the right edge instead of centered, for content too tall/wide for a
 * centered modal (e.g. a list + an inline detail panel).
 *
 * Callers render their own content as children — this component only owns
 * the shell and header, never business logic.
 */
export function Drawer({ icon: Icon, title, onClose, closeLabel, children }: DrawerProps) {
  const titleId = useId();

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

  return (
    <div
      className="fixed inset-0 z-40 flex justify-end bg-black/50 backdrop-blur-xs animate-in fade-in-0"
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
    >
      <div className="fixed inset-0" aria-hidden="true" onClick={onClose} />

      <div className="relative flex h-full w-full max-w-lg flex-col overflow-y-auto rounded-l-2xl border-l bg-card shadow-2xl duration-300 animate-in slide-in-from-right ease-out">
        <div className="sticky top-0 z-10 flex items-center justify-between border-b bg-card px-6 py-4">
          <div className="flex items-center gap-2.5">
            <div className="flex size-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <Icon className="size-4" aria-hidden="true" />
            </div>
            <h2 id={titleId} className="text-lg font-bold text-foreground">
              {title}
            </h2>
          </div>
          <Button variant="ghost" size="icon-sm" onClick={onClose} aria-label={closeLabel}>
            <X className="size-4" aria-hidden="true" />
          </Button>
        </div>

        <div className="flex flex-1 flex-col p-6">{children}</div>
      </div>
    </div>
  );
}
