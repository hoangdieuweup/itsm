"use client";

import { useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { LogIn, AlertCircle } from "lucide-react";

import { Button } from "@/shared/ui/button";
import { m } from "@/shared/lib/motion";
import { API_CONFIG } from "@/shared/constants/api";
import { BrandPanel } from "./brand-panel";
import { LanguageSwitch } from "./language-switch";

export function LoginForm() {
  const t = useTranslations("auth");
  const tc = useTranslations("common.meta");
  const te = useTranslations("common.errors");
  const searchParams = useSearchParams();

  const errorCode = searchParams.get("error");

  function handleSsoLogin() {
    window.location.href = API_CONFIG.ENDPOINTS.AUTH.SSO_START;
  }

  return (
    <div className="flex min-h-[100dvh] w-full">
      <BrandPanel />

      {/* ── Right pane: login form ── */}
      <div className="flex w-full flex-col items-center justify-center bg-gray-50/50 px-6 sm:px-12 lg:w-[52%]">
        <m.div
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35, delay: 0.15, ease: "easeOut" }}
          className="w-full max-w-md"
        >
          {/* ── Language switch ── */}
          <div className="mb-12 flex justify-end">
            <LanguageSwitch />
          </div>

          {/* ── Heading ── */}
          <div className="mb-8 space-y-3">
            <h1 className="font-heading text-3xl font-bold tracking-tight text-gray-900 sm:text-4xl">
              {t("login.title")}
            </h1>
            <p className="text-[15px] leading-relaxed text-gray-500">
              {t("login.subtitle")}
            </p>
          </div>

          {/* ── SSO error banner ── */}
          {errorCode && (
            <div
              role="alert"
              className="mb-6 flex items-start gap-2.5 rounded-lg border border-red-200 bg-red-50 p-3 text-sm text-red-700"
            >
              <AlertCircle className="mt-0.5 size-4 shrink-0" aria-hidden />
              <span>
                {te.has(errorCode as Parameters<typeof te>[0])
                  ? te(errorCode as Parameters<typeof te>[0])
                  : te("unknown")}
              </span>
            </div>
          )}

          {/* ── CTA button ── */}
          <Button
            size="lg"
            onClick={handleSsoLogin}
            className="h-12 w-full cursor-pointer justify-center gap-2.5 rounded-xl bg-[#2563EB] text-base font-semibold text-white shadow-lg shadow-blue-600/25 transition-all duration-200 hover:bg-[#1D4ED8] hover:shadow-xl hover:shadow-blue-600/30"
          >
            <LogIn className="size-4" aria-hidden />
            {t("login.continueButton")}
          </Button>

          {/* ── Footer ── */}
          <p className="mt-10 text-center text-xs text-gray-400">
            {tc("copyright", { year: new Date().getFullYear() })}
          </p>
        </m.div>
      </div>
    </div>
  );
}
