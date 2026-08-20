"use client";

import { useTranslations } from "next-intl";
import { ApiRequestError } from "@/shared/lib/api-client";

/**
 * Translates an API error into a user-facing message via i18n.
 *
 * - If the error is an `ApiRequestError` and a translation exists for its
 *   `code`, that translation is returned.
 * - Otherwise the non-localized `error.message` is used as a fallback so a
 *   new backend error code doesn't crash the UI while translators catch up.
 * - Non-API errors get the generic "unknown" message.
 *
 * Lives in `shared/lib/` because it's generic infrastructure, not owned by
 * any one module — per nextjs-modular-architecture's i18n-and-errors.md.
 */
export function useApiErrorMessage() {
  const t = useTranslations("common.errors");

  return (error: unknown): string => {
    if (error instanceof ApiRequestError && t.has(error.code)) {
      return t(error.code as Parameters<typeof t>[0]);
    }
    if (error instanceof ApiRequestError) {
      return error.message;
    }
    return t("unknown");
  };
}
