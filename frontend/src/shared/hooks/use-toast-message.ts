"use client";

import { useTranslations } from "next-intl";
import { toast } from "@/shared/ui/sonner";
import { useApiErrorMessage } from "@/shared/lib/handle-api-error";

/**
 * Returns `{ success, error }` callbacks for mutation hooks.
 *
 * - `success(key)` shows a translated success toast from the module namespace.
 * - `error(err)` resolves the backend error code via `useApiErrorMessage`
 *   and shows a translated error toast.
 *
 * Usage in a mutation hook:
 * ```ts
 * const { success, error } = useToastMessage("roles");
 * return useMutation({
 *   ...
 *   onSuccess: () => { invalidate(); success("created"); },
 *   onError: error,
 * });
 * ```
 */
export function useToastMessage(moduleNamespace: string) {
  const t = useTranslations(moduleNamespace);
  const getErrorMessage = useApiErrorMessage(moduleNamespace);

  return {
    success: (messageKey: string) => {
      const fullKey = `messages.${messageKey}` as Parameters<typeof t>[0];
      toast.success(t.has(fullKey) ? t(fullKey) : messageKey);
    },
    error: (err: unknown) => {
      toast.error(getErrorMessage(err));
    },
  };
}
