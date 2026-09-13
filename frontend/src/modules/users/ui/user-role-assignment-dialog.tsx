"use client";

import { useState, useMemo } from "react";
import { useTranslations } from "next-intl";
import { Check, Lock } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { Skeleton } from "@/shared/ui/skeleton";
import { Dialog, DialogErrorAlert } from "@/shared/ui/dialog";
import { useApiErrorMessage } from "@/shared/lib/handle-api-error";
import { useCan } from "@/entities/permission";
import type { User } from "@/entities/user";
import {
  useRolesQuery,
  isProtectedAdminRole,
  SYSTEM_ROLE_NAMES,
  type Role,
} from "@/entities/role";
import { useAssignUserRoles } from "../hooks/use-assign-user-roles";
import { IconPermission } from "@/shared/ui/icons";

interface UserRoleAssignmentDialogProps {
  isOpen: boolean;
  onClose: () => void;
  user: User | null;
}

export function UserRoleAssignmentDialog({
  isOpen,
  onClose,
  user,
}: UserRoleAssignmentDialogProps) {
  if (!isOpen || !user) return null;

  return <UserRoleAssignmentInner key={`user-roles-${user.id}`} user={user} onClose={onClose} />;
}

function UserRoleAssignmentInner({
  user,
  onClose,
}: {
  user: User;
  onClose: () => void;
}) {
  const t = useTranslations("users");
  const tRoles = useTranslations("roles");
  const getErrorMessage = useApiErrorMessage("users");
  const canAssignRole = useCan("user", "assign_role");
  const {
    data: rolesPage,
    isLoading: isRolesLoading,
    error: rolesFetchError,
  } = useRolesQuery(100, 0, Boolean(user));
  const assignRoles = useAssignUserRoles();

  const availableRoles = useMemo(() => rolesPage?.items ?? [], [rolesPage]);

  const userRoleNamesSet = useMemo(
    () =>
      new Set(
        user.roleNames && user.roleNames.length > 0
          ? user.roleNames
          : user.roleName
            ? [user.roleName]
            : [SYSTEM_ROLE_NAMES.MEMBER],
      ),
    [user],
  );

  const defaultRoleIds = useMemo(() => {
    const ids = new Set<string>();
    for (const r of availableRoles) {
      if (userRoleNamesSet.has(r.name)) {
        ids.add(r.id);
      }
    }
    return ids;
  }, [availableRoles, userRoleNamesSet]);

  const [customRoleIds, setCustomRoleIds] = useState<Set<string> | null>(null);
  const selectedRoleIds = customRoleIds ?? defaultRoleIds;

  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const isTargetAdmin = isProtectedAdminRole(user.roleName) || user.roleNames?.includes(SYSTEM_ROLE_NAMES.ADMIN);

  const toggleRole = (role: Role) => {
    if (!canAssignRole) return;

    if (isTargetAdmin && role.name === SYSTEM_ROLE_NAMES.ADMIN && selectedRoleIds.has(role.id)) {
      return;
    }

    setCustomRoleIds(() => {
      const next = new Set(selectedRoleIds);
      if (next.has(role.id)) {
        next.delete(role.id);
      } else {
        next.add(role.id);
      }
      return next;
    });
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!canAssignRole) return;
    setErrorMessage(null);

    assignRoles.mutate(
      {
        userId: user.id,
        roleIds: Array.from(selectedRoleIds),
      },
      {
        onSuccess: () => {
          onClose();
        },
        onError: (err) => {
          setErrorMessage(getErrorMessage(err));
        },
      },
    );
  };

  return (
    <Dialog
      icon={IconPermission}
      title={t("actions.assignRolesDialogTitle")}
      onClose={onClose}
      closeLabel={t("actions.closeRolesDialog")}
      size="lg"
      disableClose={assignRoles.isPending}
    >
      {/* Body */}
      <form onSubmit={handleSubmit} className="flex flex-1 min-h-0 flex-col overflow-hidden">
        <div className="flex flex-1 min-h-0 flex-col gap-5 overflow-y-auto px-7 sm:px-8 py-5">
          {/* Error Banner */}
          {(errorMessage || rolesFetchError) && (
            <DialogErrorAlert
              message={errorMessage || (rolesFetchError ? getErrorMessage(rolesFetchError) : "")}
            />
          )}

          {/* Protected Admin Notice */}
          {isTargetAdmin && (
            <div className="flex items-start gap-2.5 rounded-2xl border border-amber-500/20 bg-amber-500/10 p-4 text-xs text-amber-800 dark:text-amber-300">
              <Lock className="size-4.5 shrink-0 mt-0.5" />
              <span>{t("actions.adminRoleProtected")}</span>
            </div>
          )}

          <p className="text-sm text-muted-foreground">
            {t("actions.assignRolesDescription", { name: user.name, email: user.email })}
          </p>

          {/* Roles Checkbox List */}
          {isRolesLoading ? (
            <div className="flex flex-col gap-2 py-4">
              <Skeleton className="h-12 w-full rounded-2xl" />
              <Skeleton className="h-12 w-full rounded-2xl" />
            </div>
          ) : (
            <div className="flex flex-col gap-2.5">
              {availableRoles.map((role) => {
                const isChecked = selectedRoleIds.has(role.id);
                const isLockedAdmin =
                  isTargetAdmin && role.name === SYSTEM_ROLE_NAMES.ADMIN;

                return (
                  <div
                    key={role.id}
                    onClick={() => toggleRole(role)}
                    className={`flex cursor-pointer items-center justify-between rounded-2xl border p-3.5 transition-colors select-none ${
                      isChecked
                        ? "border-blue-500/40 bg-blue-500/10 text-foreground font-medium dark:border-blue-500/30 dark:bg-blue-500/15 shadow-2xs"
                        : "border-border/40 bg-card/60 hover:border-border/70 hover:bg-muted/40"
                    } ${isLockedAdmin ? "cursor-not-allowed opacity-90" : ""}`}
                  >
                    <div className="flex items-center gap-3">
                      <div
                        className={`flex size-5 shrink-0 items-center justify-center rounded-lg border transition-colors ${
                          isChecked
                            ? "border-blue-600 bg-blue-600 text-white dark:border-blue-500 dark:bg-blue-500 shadow-2xs"
                            : "border-muted-foreground/30 bg-background"
                        }`}
                      >
                        {isChecked && <Check className="size-3 stroke-[3]" />}
                      </div>

                      <div className="flex flex-col">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-bold text-foreground">
                            {role.name}
                          </span>
                          <span
                            className={`rounded-md px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider ${
                              role.isSystem
                                ? "border border-amber-500/30 bg-amber-50 text-amber-700 dark:border-amber-500/20 dark:bg-amber-950/60 dark:text-amber-300"
                                : "border border-border/60 bg-muted/60 text-muted-foreground"
                            }`}
                          >
                            {role.isSystem ? tRoles("types.system") : tRoles("types.custom")}
                          </span>
                        </div>
                        <span className="text-xs text-muted-foreground">
                          {tRoles("permissionsCount", { count: role.permissions.length })}
                        </span>
                      </div>
                    </div>

                    {isLockedAdmin && (
                      <span className="flex items-center gap-1 text-[11px] font-medium text-amber-600 dark:text-amber-400">
                        <Lock className="size-3.5" />
                      </span>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Footer - Pinned nicely at bottom */}
        <div className="flex shrink-0 items-center justify-end gap-3 border-t border-border/30 bg-card/80 px-7 sm:px-8 py-4 backdrop-blur-md">
          <Button
            type="button"
            variant="outline"
            onClick={onClose}
            disabled={assignRoles.isPending}
            className="rounded-xl font-medium"
          >
            {tRoles("form.cancel")}
          </Button>
          <Button
            type="submit"
            disabled={assignRoles.isPending || !canAssignRole}
            className="rounded-xl bg-blue-600 font-semibold text-white hover:bg-blue-700 dark:bg-blue-600 dark:hover:bg-blue-700 shadow-xs cursor-pointer"
          >
            {assignRoles.isPending ? t("actions.savingRoles") : t("actions.saveRoles")}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
