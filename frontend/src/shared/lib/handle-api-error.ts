"use client";

import { useTranslations } from "next-intl";
import { ApiRequestError } from "@/shared/lib/api-client";

/**
 * Translates an API error into a user-facing message via i18n.
 *
 * - When `moduleNamespace` is provided (e.g. "users", "roles", "auth"), it checks
 *   `{moduleNamespace}.errors.{code}` or `{moduleNamespace}.{code}` first.
 * - Otherwise checks `common.errors.{code}`.
 * - Falls back to `error.message` or `common.errors.unknown`.
 */
export function useApiErrorMessage(moduleNamespace?: string) {
  const tModule = useTranslations(moduleNamespace || "common");
  const tCommon = useTranslations("common.errors");

  return (error: unknown): string => {
    if (error instanceof ApiRequestError) {
      if (moduleNamespace && tModule.has(`errors.${error.code}`)) {
        return tModule(`errors.${error.code}` as Parameters<typeof tModule>[0]);
      }
      if (moduleNamespace && tModule.has(error.code)) {
        return tModule(error.code as Parameters<typeof tModule>[0]);
      }
      if (tCommon.has(error.code)) {
        return tCommon(error.code as Parameters<typeof tCommon>[0]);
      }
      return error.message;
    }
    return tCommon("unknown");
  };
}
