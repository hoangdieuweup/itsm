"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { AlertCircle } from "lucide-react";
import { Avatar, AvatarFallback } from "@/shared/ui/avatar";
import { Button } from "@/shared/ui/button";
import { ConfirmDialog } from "@/shared/ui/confirm-dialog";
import { useApiErrorMessage } from "@/shared/lib/handle-api-error";
import { formatDatetime } from "@/shared/lib/datetime";
import { Can, RESOURCES, ACTIONS } from "@/entities/permission";
import { USER_STATUS, useUsers, type User } from "@/entities/user";
import { IconUsers } from "@/shared/ui/icons";

import { SYSTEM_ROLE_NAMES } from "@/shared/constants/roles";
import { useUpdateUserStatus } from "../hooks/use-update-user-status";
import { UserRoleAssignmentDialog } from "./user-role-assignment-dialog";
import { UserRolesCell } from "./user-roles-cell";

import { m } from "@/shared/lib/motion";

import { Pagination } from "@/shared/ui/pagination";

export function UsersPageContent() {
  const t = useTranslations("users");
  const tCommon = useTranslations("common.confirmDialog");
  const getErrorMessage = useApiErrorMessage("users");
  const [limit, setLimit] = useState(50);
  const [offset, setOffset] = useState(0);
  const { data: page } = useUsers(limit, offset);
  const updateStatus = useUpdateUserStatus();
  const [userToToggle, setUserToToggle] = useState<User | null>(null);
  const [userToAssignRoles, setUserToAssignRoles] = useState<User | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const currentPage = Math.floor(offset / limit) + 1;

  const handleToggleStatus = (user: User) => {
    setUserToToggle(user);
  };

  const handleConfirmToggle = () => {
    if (!userToToggle) return;
    setErrorMessage(null);
    const nextStatus =
      userToToggle.status === USER_STATUS.BLOCKED
        ? USER_STATUS.ACTIVE
        : USER_STATUS.BLOCKED;

    updateStatus.mutate(
      { userId: userToToggle.id, status: nextStatus },
      {
        onSuccess: () => {
          setUserToToggle(null);
        },
        onError: (err) => {
          setUserToToggle(null);
          setErrorMessage(getErrorMessage(err));
        },
      },
    );
  };

  return (
    <m.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="flex flex-1 min-h-0 flex-col gap-4"
    >
      {/* Header */}
      <div className="shrink-0 flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-2xl font-extrabold tracking-tight text-foreground sm:text-3xl">
              {t("title")}
            </h1>
            <span className="inline-flex items-center rounded-full border border-blue-500/30 bg-blue-500/15 px-2.5 py-0.5 font-mono text-xs font-bold text-blue-600 dark:text-blue-400">
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
          className="shrink-0 flex items-center gap-3 rounded-2xl border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive backdrop-blur-md"
        >
          <AlertCircle className="size-4 shrink-0" aria-hidden />
          <span>{errorMessage}</span>
        </div>
      )}

      {/* Table Container - High Tech Glass Card */}
      <div className="flex flex-1 min-h-0 flex-col overflow-hidden rounded-3xl border border-border/50 bg-card/75 backdrop-blur-xl shadow-lg shadow-black/5 dark:shadow-black/20">
        <div className="flex-1 overflow-auto">
          <table className="w-full min-w-[700px] text-left text-sm">
            <thead className="sticky top-0 z-10 border-b border-border/40 bg-card/95 backdrop-blur-md text-[11px] font-bold uppercase tracking-wider text-muted-foreground/90">
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
            <tbody className="divide-y divide-border/40">
              {page.items.length === 0 ? (
                <tr>
                  <td
                    colSpan={6}
                    className="px-6 py-16 text-center text-muted-foreground"
                  >
                    <div className="flex flex-col items-center justify-center gap-2.5">
                      <IconUsers className="size-12 shrink-0 rounded-2xl shadow-xs" />
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
                      className="transition-colors hover:bg-muted/40"
                    >
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-3.5">
                          <Avatar className="size-10 border border-border/80 shadow-2xs">
                            <AvatarFallback className="bg-blue-500/10 text-xs font-bold text-blue-600 dark:bg-blue-950 dark:text-blue-400">
                              {initials}
                            </AvatarFallback>
                          </Avatar>
                          <div className="flex flex-col">
                            <span className="font-semibold text-foreground">
                              {user.name}
                            </span>
                            <span className="text-xs text-muted-foreground font-mono">
                              {user.email}
                            </span>
                          </div>
                        </div>
                      </td>
                      <td className="px-6 py-4">
                        <UserRolesCell
                          roles={
                            user.roleNames && user.roleNames.length > 0
                              ? user.roleNames
                              : [user.roleName || SYSTEM_ROLE_NAMES.MEMBER]
                          }
                          userName={user.name}
                          onAssignRoles={() => setUserToAssignRoles(user)}
                          canAssign={true}
                        />
                      </td>
                      <td className="px-6 py-4">
                        {user.employeeCode ? (
                          <span className="inline-flex rounded-lg border border-border/60 bg-muted/50 px-2 py-0.5 font-mono text-xs font-medium text-foreground">
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
                              ? "border-rose-500/30 bg-rose-500/15 text-rose-700 dark:text-rose-300"
                              : "border-emerald-500/30 bg-emerald-500/15 text-emerald-700 dark:text-emerald-300"
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
                      <td className="px-6 py-4 text-xs font-mono text-muted-foreground">
                        {user.lastLoginAt
                          ? formatDatetime(user.lastLoginAt)
                          : "—"}
                      </td>
                      <td className="px-6 py-4 text-right">
                        <div className="flex items-center justify-end gap-2">
                          <Can I={ACTIONS.ASSIGN_ROLE} a={RESOURCES.USER}>
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => setUserToAssignRoles(user)}
                              className="font-medium shadow-2xs hover:border-primary/40"
                            >
                              {t("actions.assignRoles")}
                            </Button>
                          </Can>
                          <Can I={ACTIONS.UPDATE_STATUS} a={RESOURCES.USER}>
                            <Button
                              size="sm"
                              variant={isBlocked ? "outline" : "destructive"}
                              disabled={isUpdating}
                              onClick={() => handleToggleStatus(user)}
                              className="font-medium shadow-2xs"
                            >
                              {isUpdating
                                ? t("actions.blocking")
                                : isBlocked
                                  ? t("actions.unblock")
                                  : t("actions.block")}
                            </Button>
                          </Can>
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        <div className="shrink-0">
          <Pagination
            page={currentPage}
            pageSize={limit}
            total={page.total}
            pageSizeOptions={[10, 20, 50, 100]}
            onPageChange={(newPage) => setOffset((newPage - 1) * limit)}
            onPageSizeChange={(newLimit) => {
              setLimit(newLimit);
              setOffset(0);
            }}
          />
        </div>
      </div>

      {/* User Role Assignment Dialog */}
      <UserRoleAssignmentDialog
        isOpen={Boolean(userToAssignRoles)}
        onClose={() => setUserToAssignRoles(null)}
        user={userToAssignRoles}
      />

      {/* User Status Toggle Confirmation Dialog */}
      <ConfirmDialog
        isOpen={Boolean(userToToggle)}
        onClose={() => setUserToToggle(null)}
        onConfirm={handleConfirmToggle}
        title={
          userToToggle?.status === USER_STATUS.BLOCKED
            ? t("actions.unblockDialogTitle")
            : t("actions.blockDialogTitle")
        }
        description={
          userToToggle ? (
            <span>
              {userToToggle.status === USER_STATUS.BLOCKED
                ? t("actions.unblockConfirm")
                : t("actions.blockConfirm")}{" "}
              <strong className="font-semibold text-foreground">
                ({userToToggle.email})
              </strong>
            </span>
          ) : (
            ""
          )
        }
        confirmText={
          userToToggle?.status === USER_STATUS.BLOCKED
            ? t("actions.unblock")
            : t("actions.block")
        }
        cancelText={tCommon("cancel")}
        variant={
          userToToggle?.status === USER_STATUS.BLOCKED ? "default" : "destructive"
        }
        isLoading={updateStatus.isPending}
      />
    </m.div>
  );
}
