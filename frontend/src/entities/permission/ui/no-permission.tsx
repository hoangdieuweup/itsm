"use client";

import { ErrorView } from "@/shared/ui/error-view";

export function NoPermission() {
  return <ErrorView status="403" showBack showDashboard />;
}

