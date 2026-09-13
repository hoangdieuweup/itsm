"use client";

import { useAuthSession } from "@/modules/auth";
import { DashboardView } from "@/modules/dashboard";

export default function DashboardPage() {
  const { data: session } = useAuthSession();
  return <DashboardView userName={session.user?.name} roleName={session.roleName} />;
}
