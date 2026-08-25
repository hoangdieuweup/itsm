"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Plus, Shield, Edit2, Trash2, AlertCircle, Key, Eye } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { ConfirmDialog } from "@/shared/ui/confirm-dialog";
import { Can, RESOURCES, ACTIONS } from "@/entities/permission";
import { useApiErrorMessage } from "@/shared/lib/handle-api-error";
import { useRoles, isProtectedAdminRole, type Role } from "@/entities/role";
import { useDeleteRole } from "../hooks/use-delete-role";
import { RoleFormDialog } from "./role-form-dialog";
import { RolePermissionsCell } from "./role-permissions-cell";
import { IconPermission } from "@/shared/ui/icons";

import { m } from "@/shared/lib/motion";

export function RolesPageContent() {
  const t = useTranslations("roles");
  const tCommon = useTranslations("common.confirmDialog");
  const getErrorMessage = useApiErrorMessage("roles");
  const { data: page } = useRoles(50, 0);
  const deleteRole = useDeleteRole();

  const [dialogOpen, setDialogOpen] = useState(false);
  const [selectedRole, setSelectedRole] = useState<Role | null>(null);
  const [roleToDelete, setRoleToDelete] = useState<Role | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const handleCreate = () => {
    setSelectedRole(null);
    setDialogOpen(true);
  };

  const handleEdit = (role: Role) => {
    setSelectedRole(role);
    setDialogOpen(true);
  };

  const handleDelete = (role: Role) => {
    setRoleToDelete(role);
  };

  const handleConfirmDelete = () => {
    if (!roleToDelete) return;
    setErrorMessage(null);
    deleteRole.mutate(roleToDelete.id, {
      onSuccess: () => {
        setRoleToDelete(null);
      },
      onError: (err) => {
        setRoleToDelete(null);
        setErrorMessage(getErrorMessage(err));
      },
    });
  };

  return (
    <m.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="flex flex-1 min-h-0 flex-col gap-4"
    >
      {/* Header */}
      <div className="shrink-0 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-2xl font-extrabold tracking-tight text-foreground sm:text-3xl">
              {t("title")}
            </h1>
            <span className="inline-flex items-center rounded-full border border-purple-500/30 bg-purple-500/15 px-2.5 py-0.5 font-mono text-xs font-bold text-purple-600 dark:text-purple-400">
              {page.total}
            </span>
          </div>
          <p className="mt-1 text-sm text-muted-foreground">{t("description")}</p>
        </div>

        <Can I={ACTIONS.CREATE} a={RESOURCES.ROLE}>
          <Button
            onClick={handleCreate}
            className="gap-2 self-start bg-gradient-to-r from-blue-600 to-indigo-600 font-semibold text-white shadow-md shadow-blue-500/25 hover:from-blue-700 hover:to-indigo-700 sm:self-auto"
          >
            <Plus className="size-4" />
            {t("createRole")}
          </Button>
        </Can>
      </div>

      {/* Error alert if delete fails */}
      {errorMessage && (
        <div
          role="alert"
          className="shrink-0 flex items-center justify-between rounded-2xl border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive backdrop-blur-md"
        >
          <div className="flex items-center gap-2">
            <AlertCircle className="size-4 shrink-0 text-destructive" />
            <span>{errorMessage}</span>
          </div>
          <button
            onClick={() => setErrorMessage(null)}
            className="text-xs text-destructive hover:underline cursor-pointer"
          >
            {tCommon("cancel")}
          </button>
        </div>
      )}

      {/* Roles List Table - High Tech Glass Card */}
      <div className="flex flex-1 min-h-0 flex-col overflow-hidden rounded-3xl border border-border/50 bg-card/75 backdrop-blur-xl shadow-lg shadow-black/5 dark:shadow-black/20">
        <div className="flex-1 overflow-auto">
          <table className="w-full text-left text-sm">
            <thead className="sticky top-0 z-10 border-b border-border/40 bg-card/95 backdrop-blur-md text-[11px] font-bold uppercase tracking-wider text-muted-foreground/90">
              <tr>
                <th className="px-6 py-4 font-bold text-foreground/80">{t("columns.name")}</th>
                <th className="px-6 py-4 font-bold text-foreground/80">{t("columns.type")}</th>
                <th className="px-6 py-4 font-bold text-foreground/80">{t("columns.permissions")}</th>
                <th className="px-6 py-4 text-right font-bold text-foreground/80">{t("columns.actions")}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/40">
              {page.items.length === 0 ? (
                <tr>
                  <td colSpan={4} className="px-6 py-16 text-center text-muted-foreground">
                    <div className="flex flex-col items-center justify-center gap-2.5">
                      <div className="flex size-12 items-center justify-center rounded-2xl bg-muted/60">
                        <Shield className="size-6 text-muted-foreground/60" />
                      </div>
                      <p className="font-medium">{t("empty")}</p>
                    </div>
                  </td>
                </tr>
              ) : (
                page.items.map((role) => {
                  const isSystem = role.isSystem;
                  const isDeleting =
                    deleteRole.isPending && deleteRole.variables === role.id;

                  return (
                    <tr
                      key={role.id}
                      className="transition-colors hover:bg-muted/40"
                    >
                      <td className="px-6 py-4 font-semibold text-foreground">
                        <div className="flex items-center gap-2.5">
                          <IconPermission className="size-5 shrink-0 rounded-lg shadow-2xs" />
                          <span>{role.name}</span>
                        </div>
                      </td>
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-2">
                          <span
                            className={`inline-flex items-center rounded-lg px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wider ${
                              isSystem
                                ? "border border-indigo-500/30 bg-indigo-500/15 text-indigo-700 dark:text-indigo-300 shadow-2xs"
                                : "border border-border/70 bg-muted/60 text-foreground"
                            }`}
                          >
                            {isSystem ? t("types.system") : t("types.custom")}
                          </span>
                          {isProtectedAdminRole(role) && (
                            <span className="inline-flex items-center gap-1 rounded-lg border border-amber-500/40 bg-amber-500/15 px-2 py-0.5 text-[11px] font-semibold text-amber-700 dark:text-amber-300 shadow-2xs" title={t("actions.adminProtectedTooltip")}>
                              <Key className="size-3" />
                              {t("badges.adminProtected")}
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="px-6 py-4">
                        <RolePermissionsCell
                          permissions={role.permissions}
                          roleName={role.name}
                          isSystem={role.isSystem}
                        />
                      </td>
                      <td className="px-6 py-4 text-right">
                        <div className="flex items-center justify-end gap-1">
                          <Can I={ACTIONS.UPDATE} a={RESOURCES.ROLE}>
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() => handleEdit(role)}
                              className="size-8 p-0 text-muted-foreground hover:text-foreground"
                              title={isProtectedAdminRole(role) ? t("actions.view") : t("actions.edit")}
                            >
                              {isProtectedAdminRole(role) ? (
                                <Eye className="size-3.5" />
                              ) : (
                                <Edit2 className="size-3.5" />
                              )}
                              <span className="sr-only">
                                {isProtectedAdminRole(role) ? t("actions.view") : t("actions.edit")} {role.name}
                              </span>
                            </Button>
                          </Can>

                          {!role.isSystem && (
                            <Can I={ACTIONS.DELETE} a={RESOURCES.ROLE}>
                              <Button
                                size="sm"
                                variant="ghost"
                                disabled={isDeleting}
                                onClick={() => handleDelete(role)}
                                className="size-8 p-0 text-rose-600 hover:bg-rose-500/10 hover:text-rose-700 dark:hover:bg-rose-950/50"
                                title={t("actions.delete")}
                              >
                                <Trash2 className="size-3.5" />
                                <span className="sr-only">
                                  {t("actions.delete")} {role.name}
                                </span>
                              </Button>
                            </Can>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Create / Edit Dialog */}
      <RoleFormDialog
        isOpen={dialogOpen}
        onClose={() => setDialogOpen(false)}
        role={selectedRole}
      />

      {/* Delete Confirmation Dialog */}
      <ConfirmDialog
        isOpen={Boolean(roleToDelete)}
        onClose={() => setRoleToDelete(null)}
        onConfirm={handleConfirmDelete}
        title={t("actions.deleteDialogTitle")}
        description={
          roleToDelete ? (
            <span>
              {t("actions.deleteConfirm")}{" "}
              <strong className="font-semibold text-foreground">
                ({roleToDelete.name})
              </strong>
            </span>
          ) : (
            ""
          )
        }
        confirmText={t("actions.delete")}
        cancelText={tCommon("cancel")}
        variant="destructive"
        isLoading={deleteRole.isPending}
      />
    </m.div>
  );
}
