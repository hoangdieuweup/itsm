"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { AlertCircle, Users } from "lucide-react";
import { Avatar, AvatarFallback } from "@/shared/ui/avatar";
import { Button } from "@/shared/ui/button";
import { useApiErrorMessage } from "@/shared/lib/handle-api-error";
import { Can } from "@/entities/permission";
import { USER_STATUS, type User } from "@/entities/user";
import { useUsers } from "../api/use-users";
import { useUpdateUserStatus } from "../hooks/use-update-user-status";

export function UsersPageContent() {
  const t = useTranslations("users");
  const getErrorMessage = useApiErrorMessage("users");
  const { data: page } = useUsers(50, 0);
  const updateStatus = useUpdateUserStatus();
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const handleToggleStatus = (user: User) => {
    setErrorMessage(null);
    const nextStatus =
      user.status === USER_STATUS.BLOCKED
        ? USER_STATUS.ACTIVE
        : USER_STATUS.BLOCKED;

    updateStatus.mutate(
      { userId: user.id, status: nextStatus },
      {
        onError: (err) => {
          setErrorMessage(getErrorMessage(err));
        },
      },
    );
  };

  return (
    <div className="flex flex-1 flex-col gap-6">
      {/* Header */}
      <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-2xl font-bold tracking-tight text-foreground sm:text-3xl">
              {t("title")}
            </h1>
            <span className="inline-flex items-center rounded-full border border-blue-200 bg-blue-50 px-2.5 py-0.5 text-xs font-semibold text-blue-700 dark:border-blue-800 dark:bg-blue-950 dark:text-blue-300">
              {page.total}
            </span>
          </div>
          <p className="mt-1 text-sm text-muted-foreground">{t("description")}</p>
        </div>
      </div>

      {/* Error alert if any mutation fails */}
      {errorMessage && (
        <div
          role="alert"
          className="flex items-center gap-3 rounded-xl border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive"
        >
          <AlertCircle className="size-4 shrink-0" aria-hidden />
          <span>{errorMessage}</span>
        </div>
      )}

      {/* Table Container - fully responsive */}
      <div className="overflow-hidden rounded-2xl bg-card shadow-xs">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[700px] text-left text-sm">
            <thead className="bg-muted/40 text-xs font-bold uppercase tracking-wider text-muted-foreground/90">
              <tr>
                <th scope="col" className="px-6 py-4 font-bold text-foreground/80">
                  {t("columns.name")}
                </th>
                <th scope="col" className="px-6 py-4 font-bold text-foreground/80">
                  {t("columns.role")}
                </th>
                <th scope="col" className="px-6 py-4 font-bold text-foreground/80">
                  {t("columns.employeeCode")}
                </th>
                <th scope="col" className="px-6 py-4 font-bold text-foreground/80">
                  {t("columns.status")}
                </th>
                <th scope="col" className="px-6 py-4 font-bold text-foreground/80">
                  {t("columns.lastLogin")}
                </th>
                <th scope="col" className="px-6 py-4 text-right font-bold text-foreground/80">
                  {t("columns.actions")}
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/60">
              {page.items.length === 0 ? (
                <tr>
                  <td
                    colSpan={6}
                    className="px-6 py-16 text-center text-muted-foreground"
                  >
                    <div className="flex flex-col items-center justify-center gap-2.5">
                      <div className="flex size-12 items-center justify-center rounded-full bg-muted">
                        <Users className="size-6 text-muted-foreground/60" />
                      </div>
                      <p className="font-medium">{t("empty")}</p>
                    </div>
                  </td>
                </tr>
              ) : (
                page.items.map((user) => {
                  const initials = user.name
                    .split(" ")
                    .map((n) => n[0])
                    .slice(0, 2)
                    .join("")
                    .toUpperCase();
                  const isBlocked = user.status === USER_STATUS.BLOCKED;
                  const isUpdating =
                    updateStatus.isPending &&
                    updateStatus.variables?.userId === user.id;

                  return (
                    <tr
                      key={user.id}
                      className="transition-colors hover:bg-muted/30"
                    >
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-3.5">
                          <Avatar className="size-10 border border-border/80 shadow-2xs">
                            <AvatarFallback className="bg-blue-50 text-xs font-bold text-blue-700 dark:bg-blue-950 dark:text-blue-300">
                              {initials}
                            </AvatarFallback>
                          </Avatar>
                          <div className="flex flex-col">
                            <span className="font-semibold text-foreground">
                              {user.name}
                            </span>
                            <span className="text-xs text-muted-foreground">
                              {user.email}
                            </span>
                          </div>
                        </div>
                      </td>
                      <td className="px-6 py-4">
                        <span
                          className={`inline-flex items-center rounded-md px-2.5 py-0.5 text-xs font-semibold uppercase tracking-wider ${
                            user.roleName === "admin"
                              ? "border border-amber-500/30 bg-amber-50 text-amber-700 dark:border-amber-500/20 dark:bg-amber-950/60 dark:text-amber-300"
                              : "border border-border/80 bg-muted/60 text-foreground"
                          }`}
                        >
                          {user.roleName || "member"}
                        </span>
                      </td>
                      <td className="px-6 py-4">
                        {user.employeeCode ? (
                          <span className="inline-flex rounded-md border border-border/60 bg-muted/50 px-2 py-0.5 font-mono text-xs font-medium text-foreground">
                            {user.employeeCode}
                          </span>
                        ) : (
                          <span className="text-xs text-muted-foreground/50">
                            —
                          </span>
                        )}
                      </td>
                      <td className="px-6 py-4">
                        <span
                          className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-semibold ${
                            isBlocked
                              ? "border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-900/60 dark:bg-rose-950/60 dark:text-rose-300"
                              : "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900/60 dark:bg-emerald-950/60 dark:text-emerald-300"
                          }`}
                        >
                          <span
                            className={`size-1.5 rounded-full ${
                              isBlocked ? "bg-rose-500" : "bg-emerald-500"
                            }`}
                          />
                          {isBlocked
                            ? t("status.blocked")
                            : t("status.active")}
                        </span>
                      </td>
                      <td className="px-6 py-4 text-xs text-muted-foreground">
                        {user.lastLoginAt
                          ? new Date(user.lastLoginAt).toLocaleString()
                          : "—"}
                      </td>
                      <td className="px-6 py-4 text-right">
                        <Can I="update_status" a="user">
                          {({ isAllowed }) => (
                            <Button
                              size="sm"
                              variant={isBlocked ? "outline" : "destructive"}
                              disabled={!isAllowed || isUpdating}
                              onClick={() => handleToggleStatus(user)}
                              className="font-medium shadow-2xs"
                            >
                              {isUpdating
                                ? t("actions.blocking")
                                : isBlocked
                                  ? t("actions.unblock")
                                  : t("actions.block")}
                            </Button>
                          )}
                        </Can>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
