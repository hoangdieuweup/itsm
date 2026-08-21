"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Plus, Shield, ShieldCheck, Edit2, Trash2, AlertCircle, Key } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { Can } from "@/entities/permission";
import { useApiErrorMessage } from "@/shared/lib/handle-api-error";
import { useRoles } from "../api/use-roles";
import { useDeleteRole } from "../hooks/use-delete-role";
import { RoleFormDialog } from "./role-form-dialog";
import type { Role } from "../model/schema";

export function RolesPageContent() {
  const t = useTranslations("roles");
  const getErrorMessage = useApiErrorMessage("roles");
  const { data: page } = useRoles(50, 0);
  const deleteRole = useDeleteRole();

  const [dialogOpen, setDialogOpen] = useState(false);
  const [selectedRole, setSelectedRole] = useState<Role | null>(null);
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
    if (!window.confirm(t("actions.deleteConfirm"))) return;
    setErrorMessage(null);
    deleteRole.mutate(role.id, {
      onError: (err) => {
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

        <Can I="create" a="role">
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
          className="flex items-center gap-2.5 rounded-xl border border-destructive/20 bg-destructive/10 p-4 text-sm text-destructive"
        >
          <AlertCircle className="size-4 shrink-0" aria-hidden />
          <span>{errorMessage}</span>
        </div>
      )}

      {/* Roles Table */}
      <div className="overflow-hidden rounded-2xl bg-card shadow-xs">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-left text-sm">
            <thead className="bg-muted/40 text-xs font-bold uppercase tracking-wider text-muted-foreground/90">
              <tr>
                <th scope="col" className="px-6 py-4 font-bold text-foreground/80">
                  {t("columns.name")}
                </th>
                <th scope="col" className="px-6 py-4 font-bold text-foreground/80">
                  {t("columns.type")}
                </th>
                <th scope="col" className="px-6 py-4 font-bold text-foreground/80">
                  {t("columns.permissions")}
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
                    colSpan={4}
                    className="px-6 py-16 text-center text-muted-foreground"
                  >
                    <div className="flex flex-col items-center justify-center gap-2.5">
                      <div className="flex size-12 items-center justify-center rounded-full bg-muted">
                        <Key className="size-6 text-muted-foreground/60" />
                      </div>
                      <p className="font-medium">{t("empty")}</p>
                    </div>
                  </td>
                </tr>
              ) : (
                page.items.map((role) => {
                  const isDeleting =
                    deleteRole.isPending &&
                    deleteRole.variables === role.id;

                  return (
                    <tr
                      key={role.id}
                      className="transition-colors hover:bg-muted/30"
                    >
                      <td className="px-6 py-4">
                        <div className="flex items-center gap-3">
                          <div className="flex size-8 items-center justify-center rounded-lg border border-border/80 bg-muted/60">
                            {role.isSystem ? (
                              <ShieldCheck className="size-4 text-blue-600 dark:text-blue-400" />
                            ) : (
                              <Shield className="size-4 text-muted-foreground" />
                            )}
                          </div>
                          <span className="font-semibold text-foreground">
                            {role.name}
                          </span>
                        </div>
                      </td>
                      <td className="px-6 py-4">
                        <span
                          className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold ${
                            role.isSystem
                              ? "border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-900/60 dark:bg-blue-950/60 dark:text-blue-300"
                              : "border-purple-200 bg-purple-50 text-purple-700 dark:border-purple-900/60 dark:bg-purple-950/60 dark:text-purple-300"
                          }`}
                        >
                          {role.isSystem
                            ? t("types.system")
                            : t("types.custom")}
                        </span>
                      </td>
                      <td className="px-6 py-4">
                        <span className="inline-flex rounded-md border border-border/60 bg-muted/50 px-2 py-0.5 font-mono text-xs font-semibold text-foreground">
                          {t("permissionsCount", { count: role.permissions.length })}
                        </span>
                      </td>
                      <td className="px-6 py-4 text-right">
                        <div className="flex items-center justify-end gap-1">
                          <Can I="update" a="role">
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() => handleEdit(role)}
                              className="size-8 p-0 text-muted-foreground hover:text-foreground"
                              title={t("actions.edit")}
                            >
                              <Edit2 className="size-3.5" />
                              <span className="sr-only">
                                {t("actions.edit")} {role.name}
                              </span>
                            </Button>
                          </Can>

                          {!role.isSystem && (
                            <Can I="delete" a="role">
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
    </div>
  );
}
