"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Plus, Shield, ShieldCheck, Edit2, Trash2, AlertCircle, Key, Eye } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { ConfirmDialog } from "@/shared/ui/confirm-dialog";
import { Can, RESOURCES, ACTIONS } from "@/entities/permission";
import { useApiErrorMessage } from "@/shared/lib/handle-api-error";
import { useRoles, isProtectedAdminRole, type Role } from "@/entities/role";
import { useDeleteRole } from "../hooks/use-delete-role";
import { RoleFormDialog } from "./role-form-dialog";


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
    <div className="flex flex-1 flex-col gap-6">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
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

        <Can I={ACTIONS.CREATE} a={RESOURCES.ROLE}>
          <Button
            onClick={handleCreate}
            className="gap-2 self-start bg-blue-600 font-semibold text-white shadow-xs shadow-blue-500/25 hover:bg-blue-700 sm:self-auto"
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
          className="mb-6 flex items-center justify-between rounded-lg border border-rose-200 bg-rose-50 p-4 text-sm text-rose-800 dark:border-rose-900/50 dark:bg-rose-950/50 dark:text-rose-200"
        >
          <div className="flex items-center gap-2">
            <AlertCircle className="size-4 shrink-0 text-rose-600 dark:text-rose-400" />
            <span>{errorMessage}</span>
          </div>
          <button
            onClick={() => setErrorMessage(null)}
            className="text-rose-500 hover:text-rose-700 dark:hover:text-rose-300"
          >
            &times;
          </button>
        </div>
      )}

      {/* Roles List Table */}
      <div className="rounded-xl border border-border/80 bg-card shadow-xs overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-border/60 bg-muted/40 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              <tr>
                <th className="px-6 py-3.5">{t("columns.name")}</th>
                <th className="px-6 py-3.5">{t("columns.type")}</th>
                <th className="px-6 py-3.5">{t("columns.permissions")}</th>
                <th className="px-6 py-3.5 text-right">{t("columns.actions")}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/40">
              {page.items.length === 0 ? (
                <tr>
                  <td colSpan={4} className="px-6 py-12 text-center text-muted-foreground">
                    {t("empty")}
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
                      className="transition-colors hover:bg-muted/30"
                    >
                      <td className="px-6 py-4 font-medium text-foreground">
                        <div className="flex items-center gap-2.5">
                          {isSystem ? (
                            <ShieldCheck className="size-4 shrink-0 text-indigo-500" />
                          ) : (
                            <Shield className="size-4 shrink-0 text-muted-foreground" />
                          )}
                          <span>{role.name}</span>
                        </div>
                      </td>
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-1.5">
                          <span
                            className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                              isSystem
                                ? "bg-indigo-50 text-indigo-700 dark:bg-indigo-950/50 dark:text-indigo-300"
                                : "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300"
                            }`}
                          >
                            {isSystem ? t("types.system") : t("types.custom")}
                          </span>
                          {isProtectedAdminRole(role) && (
                            <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-700 dark:bg-amber-950/50 dark:text-amber-300" title={t("actions.adminProtectedTooltip")}>
                              <Key className="size-3" />
                              {t("badges.adminProtected")}
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="px-6 py-4">
                        <span className="inline-flex rounded-md border border-border/60 bg-muted/50 px-2 py-0.5 font-mono text-xs font-semibold text-foreground">
                          {t("permissionsCount", { count: role.permissions.length })}
                        </span>
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
                                className="size-8 p-0 text-rose-600 hover:bg-rose-50 hover:text-rose-700 dark:hover:bg-rose-950/50"
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
    </div>
  );
}
