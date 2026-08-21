"use client";

import { useEffect, useCallback, useId } from "react";
import { X, AlertTriangle, AlertCircle, Info, Loader2 } from "lucide-react";
import { Button } from "@/shared/ui/button";

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

  if (!isOpen) return null;

  const getVariantStyles = () => {
    switch (variant) {
      case "destructive":
        return {
          icon: <AlertTriangle className="size-5" aria-hidden="true" />,
          iconContainer:
            "bg-rose-500/10 text-rose-600 dark:bg-rose-950/50 dark:text-rose-400 border border-rose-500/20",
          buttonVariant: "destructive" as const,
        };
      case "warning":
        return {
          icon: <AlertCircle className="size-5" aria-hidden="true" />,
          iconContainer:
            "bg-amber-500/10 text-amber-600 dark:bg-amber-950/50 dark:text-amber-400 border border-amber-500/20",
          buttonVariant: "default" as const,
        };
      case "default":
      default:
        return {
          icon: <Info className="size-5" aria-hidden="true" />,
          iconContainer:
            "bg-primary/10 text-primary border border-primary/20",
          buttonVariant: "default" as const,
        };
    }
  };

  const { icon, iconContainer, buttonVariant } = getVariantStyles();

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-xs animate-in fade-in-0"
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
      aria-describedby={descriptionId}
    >
      {/* Click outside backdrop */}
      <div
        className="fixed inset-0"
        aria-hidden="true"
        onClick={() => !isLoading && onClose()}
      />

      <div className="relative z-10 flex w-full max-w-md flex-col rounded-2xl border bg-card p-6 shadow-2xl animate-in zoom-in-95">
        {/* Close Button */}
        <button
          type="button"
          onClick={onClose}
          disabled={isLoading}
          className="absolute right-4 top-4 cursor-pointer rounded-lg p-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:opacity-50"
          aria-label="Close"
        >
          <X className="size-4" />
        </button>

        {/* Content */}
        <div className="flex items-start gap-4">
          <div
            className={`flex size-10 shrink-0 items-center justify-center rounded-xl ${iconContainer}`}
          >
            {icon}
          </div>

          <div className="flex-1 pt-0.5">
            <h2
              id={titleId}
              className="text-base font-bold text-foreground leading-tight"
            >
              {title}
            </h2>
            <div
              id={descriptionId}
              className="mt-2 text-sm text-muted-foreground leading-relaxed"
            >
              {description}
            </div>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="mt-6 flex items-center justify-end gap-3">
          <Button
            type="button"
            variant="outline"
            onClick={onClose}
            disabled={isLoading}
          >
            {cancelText}
          </Button>
          <Button
            type="button"
            variant={buttonVariant}
            onClick={onConfirm}
            disabled={isLoading || confirmDisabled}
            className={
              variant === "destructive"
                ? "bg-rose-600 font-semibold text-white shadow-xs shadow-rose-500/25 hover:bg-rose-700 dark:bg-rose-600 dark:hover:bg-rose-700"
                : undefined
            }
          >
            {isLoading && <Loader2 className="mr-2 size-4 animate-spin" />}
            {confirmText}
          </Button>
        </div>
      </div>
    </div>
  );
}
