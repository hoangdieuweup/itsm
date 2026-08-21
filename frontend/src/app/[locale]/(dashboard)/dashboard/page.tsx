"use client";

import { useTranslations } from "next-intl";
import { Users, Shield, ArrowRight, Activity, Sparkles } from "lucide-react";
import { Link } from "@/shared/lib/i18n/navigation";
import { ROUTES } from "@/shared/constants/routes";
import { Can } from "@/entities/permission";
import { useAuthSession } from "@/modules/auth";
import { Card, CardHeader, CardTitle, CardDescription } from "@/shared/ui/card";

export default function DashboardPage() {
  const { data: session } = useAuthSession();
  const tm = useTranslations("common.meta");
  const td = useTranslations("common.dashboard");
  const userName = session.user?.name ?? "User";

  return (
    <div className="flex flex-1 flex-col gap-8">
      {/* Welcome Banner */}
      <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-primary/10 via-card to-card p-6 sm:p-8 shadow-xs">
        <div className="flex flex-col gap-3">
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1 rounded-full bg-primary/15 px-3 py-1 text-xs font-semibold text-primary">
              <Sparkles className="size-3.5" />
              {session.roleName ? session.roleName.toUpperCase() : "MEMBER"}
            </span>
          </div>
          <h1 className="text-3xl font-extrabold tracking-tight text-foreground sm:text-4xl">
            {td("welcomeBack", { name: userName })}
          </h1>
          <p className="max-w-xl text-sm text-muted-foreground">
            {tm("appDescription")}
          </p>
        </div>
      </div>

      {/* Quick Navigation Cards */}
      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3">
        <Can I="read" a="user">
          <Link href={ROUTES.adminUsers} className="group">
            <Card className="h-full transition-all duration-200 hover:shadow-md shadow-xs bg-card">
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div className="flex size-10 items-center justify-center rounded-xl bg-primary/10 text-primary">
                    <Users className="size-5" />
                  </div>
                  <ArrowRight className="size-4 text-muted-foreground transition-transform duration-200 group-hover:translate-x-1 group-hover:text-primary" />
                </div>
                <CardTitle className="mt-3 text-base">
                  {td("userManagementTitle")}
                </CardTitle>
                <CardDescription className="text-xs">
                  {td("userManagementDesc")}
                </CardDescription>
              </CardHeader>
            </Card>
          </Link>
        </Can>

        <Can I="read" a="role">
          <Link href={ROUTES.adminRoles} className="group">
            <Card className="h-full transition-all duration-200 hover:shadow-md shadow-xs bg-card">
              <CardHeader>
                <div className="flex items-center justify-between">
                  <div className="flex size-10 items-center justify-center rounded-xl bg-purple-500/10 text-purple-600 dark:text-purple-400">
                    <Shield className="size-5" />
                  </div>
                  <ArrowRight className="size-4 text-muted-foreground transition-transform duration-200 group-hover:translate-x-1 group-hover:text-primary" />
                </div>
                <CardTitle className="mt-3 text-base">
                  {td("roleManagementTitle")}
                </CardTitle>
                <CardDescription className="text-xs">
                  {td("roleManagementDesc")}
                </CardDescription>
              </CardHeader>
            </Card>
          </Link>
        </Can>

        <Card className="h-full bg-muted/20 shadow-2xs">
          <CardHeader>
            <div className="flex size-10 items-center justify-center rounded-xl bg-muted text-muted-foreground">
              <Activity className="size-5" />
            </div>
            <CardTitle className="mt-3 text-base text-muted-foreground">
              {td("serviceDeskTitle")}
            </CardTitle>
            <CardDescription className="text-xs">
              {td("serviceDeskDesc")}
            </CardDescription>
          </CardHeader>
        </Card>
      </div>
    </div>
  );
}
