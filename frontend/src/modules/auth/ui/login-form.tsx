"use client";

import { useTranslations } from "next-intl";
import { LogIn } from "lucide-react";

import { Button } from "@/shared/ui/button";
import { Card } from "@/shared/ui/card";
import { m } from "@/shared/lib/motion";
import { BrandPanel } from "./brand-panel";
import { LanguageSwitch } from "./language-switch";

/**
 * Split-screen SSO login card (visual layer only — see issue #18). The CTA
 * stays disabled and does not start an OAuth flow. Sub-issue #15 (Frontend:
 * SSO wiring) wires this button up to WeUpBook DX OAuth2 + PKCE once #14
 * (backend SSO service) is merged.
 */
export function LoginForm() {
  const t = useTranslations("auth");
  const tc = useTranslations("common.meta");

  return (
    <m.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.25, ease: "easeOut" }}
      className="w-full max-w-4xl"
    >
      <Card className="flex-row gap-0 p-0 shadow-xl">
        <BrandPanel />

        <div className="flex w-full flex-col justify-center gap-6 p-8 sm:p-10 lg:w-[55%]">
          <div className="flex items-start justify-between gap-4">
            <span className="text-xs font-semibold text-orange-700">
              {t("login.departmentLabel")}
            </span>
            <LanguageSwitch />
          </div>

          <div className="space-y-2">
            <h1 className="font-heading text-2xl font-bold text-foreground sm:text-3xl">
              {t("login.title")}
            </h1>
            <p className="text-sm text-muted-foreground">
              {t("login.subtitle")}
            </p>
          </div>

          <Button
            disabled
            size="lg"
            className="h-11 w-full justify-center gap-2 rounded-xl bg-linear-to-r from-orange-700 to-red-800 text-base font-semibold text-white shadow-md hover:from-orange-800 hover:to-red-900 disabled:opacity-60"
          >
            <LogIn className="size-4" aria-hidden />
            {t("login.continueButton")}
          </Button>

          <p className="text-xs text-muted-foreground">
            {tc("copyright", { year: new Date().getFullYear() })}
          </p>
        </div>
      </Card>
    </m.div>
  );
}
