"use client";

import { useState, useMemo } from "react";
import { useTranslations } from "next-intl";
import { Shield, Check, Lock } from "lucide-react";
import { Button } from "@/shared/ui/button";
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

  const initialRoleIds = useMemo(() => {
    const userRoleNamesSet = new Set(
      user.roleNames && user.roleNames.length > 0
        ? user.roleNames
        : user.roleName
          ? [user.roleName]
          : [SYSTEM_ROLE_NAMES.MEMBER],
    );

    const ids = new Set<string>();
    for (const r of availableRoles) {
      if (userRoleNamesSet.has(r.name)) {
        ids.add(r.id);
      }
    }
    return ids;
  }, [availableRoles, user]);

  const [selectedRoleIds, setSelectedRoleIds] = useState<Set<string>>(initialRoleIds);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Check if target user has protected admin status
  const isTargetAdmin = isProtectedAdminRole(user.roleName) || user.roleNames?.includes(SYSTEM_ROLE_NAMES.ADMIN);

  const toggleRole = (role: Role) => {
    if (!canAssignRole) return;

    // If user is protected admin and this is the admin role, don't allow unchecking
    if (isTargetAdmin && role.name === SYSTEM_ROLE_NAMES.ADMIN && selectedRoleIds.has(role.id)) {
      return;
    }

    setSelectedRoleIds((prev) => {
      const next = new Set(prev);
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
      icon={Shield}
      title={t("actions.assignRolesDialogTitle")}
      onClose={onClose}
      closeLabel={t("actions.closeRolesDialog")}
      size="lg"
      disableClose={assignRoles.isPending}
    >
      {/* Body */}
      <form onSubmit={handleSubmit} className="flex flex-1 flex-col overflow-hidden">
        <div className="flex flex-1 flex-col gap-4 overflow-y-auto p-6">
          {/* Error Banner */}
          {(errorMessage || rolesFetchError) && (
            <DialogErrorAlert
              message={errorMessage || (rolesFetchError ? getErrorMessage(rolesFetchError) : "")}
            />
          )}

          {/* Protected Admin Notice */}
          {isTargetAdmin && (
            <div className="flex items-start gap-2.5 rounded-xl border border-amber-500/30 bg-amber-50/60 p-3.5 text-xs text-amber-800 dark:border-amber-500/20 dark:bg-amber-950/40 dark:text-amber-300">
              <Lock className="size-4 shrink-0 mt-0.5" />
              <span>{t("actions.adminRoleProtected")}</span>
            </div>
          )}

          <p className="text-sm text-muted-foreground">
            {t("actions.assignRolesDescription", { name: user.name, email: user.email })}
          </p>

          {/* Roles Checkbox List */}
          {isRolesLoading ? (
            <div className="flex flex-col gap-2 py-4">
              <div className="h-12 w-full animate-pulse rounded-xl bg-muted/50" />
              <div className="h-12 w-full animate-pulse rounded-xl bg-muted/50" />
            </div>
          ) : (
            <div className="flex flex-col gap-2">
              {availableRoles.map((role) => {
                const isChecked = selectedRoleIds.has(role.id);
                const isLockedAdmin =
                  isTargetAdmin && role.name === SYSTEM_ROLE_NAMES.ADMIN;

                return (
                  <div
                    key={role.id}
                    onClick={() => toggleRole(role)}
                    className={`flex cursor-pointer items-center justify-between rounded-xl border p-3.5 transition-colors select-none ${
                      isChecked
                        ? "border-primary/40 bg-primary/5 dark:border-primary/30 dark:bg-primary/10"
                        : "border-border/60 bg-muted/20 hover:bg-muted/40"
                    } ${isLockedAdmin ? "cursor-not-allowed opacity-90" : ""}`}
                  >
                    <div className="flex items-center gap-3">
                      <div
                        className={`flex size-5 shrink-0 items-center justify-center rounded border transition-colors ${
                          isChecked
                            ? "border-primary bg-primary text-primary-foreground"
                            : "border-muted-foreground/40 bg-background"
                        }`}
                      >
                        {isChecked && <Check className="size-3.5 stroke-[3]" />}
                      </div>

                      <div className="flex flex-col">
                        <div className="flex items-center gap-2">
                          <span className="text-sm font-medium text-foreground">
                            {role.name}
                          </span>
                          <span
                            className={`rounded-md px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${
                              role.isSystem
                                ? "border border-amber-500/30 bg-amber-50 text-amber-700 dark:border-amber-500/20 dark:bg-amber-950/60 dark:text-amber-300"
                                : "border border-border/80 bg-muted/60 text-muted-foreground"
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

        {/* Footer */}
        <div className="flex items-center justify-end gap-3 border-t border-border/60 bg-muted/20 px-6 py-4">
          <Button
            type="button"
            variant="outline"
            onClick={onClose}
            disabled={assignRoles.isPending}
            className="font-medium"
          >
            {tRoles("form.cancel")}
          </Button>
          <Button
            type="submit"
            disabled={assignRoles.isPending || !canAssignRole}
            className="font-medium shadow-2xs"
          >
            {assignRoles.isPending ? t("actions.savingRoles") : t("actions.saveRoles")}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
