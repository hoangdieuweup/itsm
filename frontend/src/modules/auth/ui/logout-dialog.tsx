"use client";

import { useId, useState } from "react";
import { useTranslations } from "next-intl";
import { Loader2, LogOut } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { Dialog } from "@/shared/ui/dialog";
import { Switch } from "@/shared/ui/switch";
import { cn } from "@/shared/lib/utils";
import type { LogoutVariables } from "../model/logout";

export interface LogoutDialogProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: (variables: LogoutVariables) => void;
  isPending: boolean;
}

function LogoutBadgeIcon({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "flex items-center justify-center border border-primary/20 bg-primary/10 text-primary",
        className,
      )}
    >
      <LogOut className="size-4.5" aria-hidden="true" />
    </span>
  );
}

/**
 * Confirms signing out. The switch, off by default, also ends the browser's
 * WeUp DX SSO session; it turns back off whenever the dialog is dismissed so
 * the broader sign-out is never carried over to the next attempt by accident.
 */
export function LogoutDialog({ isOpen, onClose, onConfirm, isPending }: LogoutDialogProps) {
  const t = useTranslations("auth.logoutDialog");
  const [endDxSession, setEndDxSession] = useState(false);
  const labelId = useId();
  const hintId = useId();

  if (!isOpen) return null;

  const handleClose = () => {
    setEndDxSession(false);
    onClose();
  };

  return (
    <Dialog
      icon={LogoutBadgeIcon}
      title={t("title")}
      onClose={handleClose}
      closeLabel={t("close")}
      size="md"
      disableClose={isPending}
    >
      <div className="space-y-5 px-6 py-5 sm:px-8">
        <p className="text-sm leading-relaxed text-muted-foreground">{t("description")}</p>

        <label className="flex cursor-pointer items-start gap-3.5 rounded-2xl border border-border/60 bg-muted/30 p-4 transition-colors hover:bg-muted/50">
          <Switch
            checked={endDxSession}
            onCheckedChange={setEndDxSession}
            disabled={isPending}
            aria-labelledby={labelId}
            aria-describedby={hintId}
            className="mt-0.5"
          />
          <span className="flex min-w-0 flex-col gap-1">
            <span id={labelId} className="text-sm font-medium text-foreground">
              {t("endDxSessionLabel")}
            </span>
            <span id={hintId} className="text-xs leading-relaxed text-muted-foreground">
              {t("endDxSessionHint")}
            </span>
          </span>
        </label>
      </div>

      <div className="flex shrink-0 items-center justify-end gap-3 border-t border-border/30 bg-card/80 px-6 py-4 sm:px-8">
        <Button
          type="button"
          variant="outline"
          onClick={handleClose}
          disabled={isPending}
          className="rounded-xl font-medium"
        >
          {t("cancel")}
        </Button>
        <Button
          type="button"
          onClick={() => onConfirm({ endDxSession })}
          disabled={isPending}
          className="rounded-xl font-semibold shadow-xs"
        >
          {isPending && <Loader2 className="mr-2 size-4 animate-spin" aria-hidden="true" />}
          {t("confirm")}
        </Button>
      </div>
    </Dialog>
  );
}
