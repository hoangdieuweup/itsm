"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { updateUserStatus } from "../api/fetchers";
import { usersKeys, type UserStatus } from "@/entities/user";
import { authKeys } from "@/entities/auth";
import { useToastMessage } from "@/shared/hooks/use-toast-message";

/**
 * Mutation hook for updating a user's status (active / blocked).
 * Invalidates users query list and current auth session upon success.
 */
export function useUpdateUserStatus() {
  const queryClient = useQueryClient();
  const { success, error } = useToastMessage("users");

  return useMutation({
    mutationFn: ({
      userId,
      status,
    }: {
      userId: string;
      status: UserStatus;
    }) => updateUserStatus(userId, status),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: usersKeys.all });
      queryClient.invalidateQueries({ queryKey: authKeys.session() });
      success("statusUpdated");
    },
    onError: error,
  });
}
