"use client";

import { useMutation } from "@tanstack/react-query";
import { testCloudflareAccountConnection } from "../api/fetchers";

export function useTestCloudflareAccountConnection() {
  return useMutation({
    mutationFn: (id: string) => testCloudflareAccountConnection(id),
  });
}
