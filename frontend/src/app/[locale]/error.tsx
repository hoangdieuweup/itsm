"use client";

import { useTranslations } from "next-intl";
import { useQueryErrorResetBoundary } from "@tanstack/react-query";
import { Button } from "@/shared/ui/button";

export default function RootError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const t = useTranslations("common.errors");
  const { reset: resetQueries } = useQueryErrorResetBoundary();

  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-4 p-6 text-center">
      <h2 className="text-lg font-semibold">{t("somethingWentWrong")}</h2>
      <p className="text-muted-foreground text-sm">{error.message}</p>
      <Button
        onClick={() => {
          resetQueries();
          reset();
        }}
      >
        {t("tryAgain")}
      </Button>
    </div>
  );
}
