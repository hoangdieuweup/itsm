"use client";

import { useEffect, useCallback, useId, useSyncExternalStore } from "react";
import { createPortal } from "react-dom";
import { X, AlertTriangle, AlertCircle, Info, Loader2 } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { m } from "@/shared/lib/motion";

const emptySubscribe = () => () => {};
const useIsMounted = () =>
  useSyncExternalStore(
    emptySubscribe,
    () => true,
    () => false,
  );

export interface ConfirmDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: string;
  description: string | React.ReactNode;
  confirmText?: string;
  cancelText?: string;
  variant?: "destructive" | "warning" | "default";
  isLoading?: boolean;
  confirmDisabled?: boolean;
}

export function ConfirmDialog({
  isOpen,
  onClose,
  onConfirm,
  title,
  description,
  confirmText = "Confirm",
  cancelText = "Cancel",
  variant = "destructive",
  isLoading = false,
  confirmDisabled = false,
}: ConfirmDialogProps) {
  const titleId = useId();
  const descriptionId = useId();
  const isMounted = useIsMounted();

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape" && !isLoading) {
        onClose();
      }
    },
    [onClose, isLoading],
  );

  useEffect(() => {
    if (isOpen) {
      document.addEventListener("keydown", handleKeyDown);
      return () => document.removeEventListener("keydown", handleKeyDown);
    }
  }, [isOpen, handleKeyDown]);

  if (!isMounted || !isOpen) return null;

  const getVariantStyles = () => {
    switch (variant) {
      case "destructive":
        return {
          icon: <AlertTriangle className="size-5" aria-hidden="true" />,
          iconContainer:
            "bg-rose-500/10 text-rose-600 dark:bg-rose-950/50 dark:text-rose-400 border border-rose-500/20 shadow-xs shadow-rose-500/5",
          buttonVariant: "destructive" as const,
        };
      case "warning":
        return {
          icon: <AlertCircle className="size-5" aria-hidden="true" />,
          iconContainer:
            "bg-amber-500/10 text-amber-600 dark:bg-amber-950/50 dark:text-amber-400 border border-amber-500/20 shadow-xs shadow-amber-500/5",
          buttonVariant: "default" as const,
        };
      case "default":
      default:
        return {
          icon: <Info className="size-5" aria-hidden="true" />,
          iconContainer:
            "bg-primary/10 text-primary border border-primary/20 shadow-xs shadow-primary/5",
          buttonVariant: "default" as const,
        };
    }
  };

  const { icon, iconContainer, buttonVariant } = getVariantStyles();

  return createPortal(
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 md:p-8"
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
      aria-describedby={descriptionId}
    >
      {/* Backdrop overlay */}
      <m.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.2 }}
        className="fixed inset-0 bg-black/40 backdrop-blur-sm dark:bg-black/75"
        aria-hidden="true"
        onClick={() => !isLoading && onClose()}
      />

      {/* Spacious Floating Card */}
      <m.div
        initial={{ opacity: 0, scale: 0.95, y: 10 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 10 }}
        transition={{ type: "spring", damping: 28, stiffness: 340 }}
        className="relative z-10 flex w-full max-w-md flex-col overflow-hidden rounded-3xl border border-border/30 bg-card/95 p-7 sm:p-8 shadow-[0_20px_60px_-15px_rgba(0,0,0,0.15)] dark:shadow-[0_25px_65px_-15px_rgba(0,0,0,0.6)] backdrop-blur-2xl"
      >
        {/* Close Button */}
        <button
          type="button"
          onClick={onClose}
          disabled={isLoading}
          className="absolute right-6 top-6 cursor-pointer rounded-2xl p-1.5 text-muted-foreground transition-colors hover:bg-muted/80 hover:text-foreground disabled:opacity-50"
          aria-label="Close"
        >
          <X className="size-4.5" />
        </button>

        {/* Content */}
        <div className="flex items-start gap-4">
          <div
            className={`flex size-12 shrink-0 items-center justify-center rounded-2xl ${iconContainer}`}
          >
            {icon}
          </div>

          <div className="flex-1 pt-0.5">
            <h2
              id={titleId}
              className="text-lg font-bold text-foreground leading-tight"
            >
              {title}
            </h2>
            <div
              id={descriptionId}
              className="mt-2.5 text-sm text-muted-foreground leading-relaxed"
            >
              {description}
            </div>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="mt-7 flex items-center justify-end gap-3">
          <Button
            type="button"
            variant="outline"
            onClick={onClose}
            disabled={isLoading}
            className="rounded-xl font-medium"
          >
            {cancelText}
          </Button>
          <Button
            type="button"
            variant={buttonVariant}
            onClick={onConfirm}
            disabled={isLoading || confirmDisabled}
            className={`rounded-xl font-semibold shadow-xs ${
              variant === "destructive"
                ? "bg-rose-600 text-white hover:bg-rose-700 shadow-rose-500/20 dark:bg-rose-600 dark:hover:bg-rose-700"
                : "bg-primary text-primary-foreground hover:bg-primary/90"
            }`}
          >
            {isLoading && <Loader2 className="mr-2 size-4 animate-spin" />}
            {confirmText}
          </Button>
        </div>
      </m.div>
    </div>,
    document.body,
  );
}
