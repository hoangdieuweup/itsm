"use client";

import { useTranslations } from "next-intl";
import { ShieldAlert } from "lucide-react";

export function NoPermission() {
  const t = useTranslations("common.noPermission");

  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-3 py-16 text-center">
      <div className="flex size-12 items-center justify-center rounded-xl bg-destructive/10 text-destructive">
        <ShieldAlert className="size-6" aria-hidden />
      </div>
      <h2 className="text-lg font-semibold text-foreground">{t("title")}</h2>
      <p className="max-w-sm text-sm text-muted-foreground">
        {t("description")}
      </p>
    </div>
  );
}
