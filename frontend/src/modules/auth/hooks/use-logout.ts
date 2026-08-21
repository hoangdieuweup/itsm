"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter } from "@/shared/lib/i18n/navigation";
import { ROUTES } from "@/shared/constants/routes";
import { useApiErrorMessage } from "@/shared/lib/handle-api-error";
import { logoutUser } from "../api/logout";

/**
 * Mutation hook for signing out.
 *
 * On success: clears all cached queries (so stale authenticated data doesn't
 * leak into the next session) and redirects to `/login`.
 *
 * On error: surfaces the translated error message via the callback the
 * consumer provides (typically a toast). Does NOT redirect on failure so
 * the user can retry.
 */
export function useLogout() {
  const queryClient = useQueryClient();
  const router = useRouter();
  const getErrorMessage = useApiErrorMessage();

  return useMutation({
    mutationFn: logoutUser,
    onSuccess: () => {
      queryClient.clear();
      router.replace(ROUTES.login);
    },
    onError: (error) => {
      // Consumer can read `mutation.error` or pass an `onError` override;
      // the translated message is available via `getErrorMessage(error)`.
      console.error("[logout]", getErrorMessage(error));
    },
  });
}
