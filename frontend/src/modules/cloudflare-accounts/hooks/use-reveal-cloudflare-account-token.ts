"use client";

import { useMutation } from "@tanstack/react-query";
import { revealCloudflareAccountToken } from "../api/fetchers";

export function useRevealCloudflareAccountToken() {
  return useMutation({
    mutationFn: (id: string) => revealCloudflareAccountToken(id),
  });
}
