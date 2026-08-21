"use client";

import { useState, useMemo } from "react";
import { useTranslations } from "next-intl";
import { X, Shield, AlertCircle, Check } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/input";
import { Label } from "@/shared/ui/label";
import { useApiErrorMessage } from "@/shared/lib/handle-api-error";
import { usePermissions } from "../api/use-roles";
import { useCreateRole } from "../hooks/use-create-role";
import { useUpdateRole } from "../hooks/use-update-role";
import type { Role, PermissionItem } from "../model/schema";

interface RoleFormDialogProps {
  isOpen: boolean;
  onClose: () => void;
  role?: Role | null;
}

export function RoleFormDialog({ isOpen, onClose, role }: RoleFormDialogProps) {
  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-xs animate-in fade-in-0"
      role="dialog"
      aria-modal="true"
    >
      <RoleFormInner
        key={role ? `edit-${role.id}` : "create-new"}
        role={role}
        onClose={onClose}
      />
    </div>
  );
}

function RoleFormInner({
  role,
  onClose,
}: {
  role?: Role | null;
  onClose: () => void;
}) {
  const t = useTranslations("roles");
  const getErrorMessage = useApiErrorMessage("roles");
  const { data: permissionsCatalog = [] } = usePermissions();
  const createRole = useCreateRole();
  const updateRole = useUpdateRole();

  const isEditing = Boolean(role);
  const isSystemRole = role?.isSystem ?? false;

  const [name, setName] = useState(() => role?.name ?? "");
  const [selectedIds, setSelectedIds] = useState<Set<number>>(
    () => new Set(role?.permissions.map((p) => p.id) ?? []),
  );
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const groupedPermissions = useMemo(() => {
    const groups: Record<string, PermissionItem[]> = {};
    for (const perm of permissionsCatalog) {
      const list = groups[perm.resource] ?? [];
      list.push(perm);
      groups[perm.resource] = list;
    }
    return groups;
  }, [permissionsCatalog]);

  const togglePermission = (id: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleGroup = (perms: PermissionItem[], shouldSelectAll: boolean) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      for (const p of perms) {
        if (shouldSelectAll) next.add(p.id);
        else next.delete(p.id);
      }
      return next;
    });
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);
    const permissionIds = Array.from(selectedIds);
    const callbacks = {
      onSuccess: () => onClose(),
      onError: (err: unknown) => setErrorMessage(getErrorMessage(err)),
    };

    if (isEditing && role) {
      updateRole.mutate(
        {
          roleId: role.id,
          name: isSystemRole ? undefined : name,
          permissionIds,
        },
        callbacks,
      );
    } else {
      createRole.mutate({ name, permissionIds }, callbacks);
    }
  };

  const isPending = createRole.isPending || updateRole.isPending;
  const isSubmitDisabled = isPending || !name.trim();

  return (
    <div className="flex max-h-[90vh] w-full max-w-2xl flex-col rounded-2xl border bg-card shadow-2xl animate-in zoom-in-95">
      {/* Modal Header */}
      <div className="flex items-center justify-between border-b px-6 py-4">
        <div className="flex items-center gap-2.5">
          <div className="flex size-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
            <Shield className="size-4" />
          </div>
          <h2 className="text-lg font-bold text-foreground">
            {isEditing ? t("editRole") : t("createRole")}
          </h2>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="cursor-pointer rounded-lg p-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        >
          <X className="size-5" />
        </button>
      </div>

      {/* Modal Body / Form */}
      <form
        onSubmit={handleSubmit}
        className="flex flex-1 flex-col overflow-hidden"
      >
        <div className="flex-1 space-y-6 overflow-y-auto p-6">
          {errorMessage && (
            <div
              role="alert"
              className="flex items-center gap-2 rounded-lg border border-destructive/20 bg-destructive/10 p-3 text-sm text-destructive"
            >
              <AlertCircle className="size-4 shrink-0" />
              <span>{errorMessage}</span>
            </div>
          )}

          <RoleNameField
            name={name}
            isSystemRole={isSystemRole}
            isPending={isPending}
            onChange={setName}
            label={t("form.nameLabel")}
            placeholder={t("form.namePlaceholder")}
            systemRoleHint={t("form.systemRoleHint")}
          />

          {/* Permissions List */}
          <div className="space-y-3">
            <Label>{t("form.permissionsLabel")}</Label>
            <div className="space-y-4 rounded-xl border bg-muted/20 p-4">
              {Object.entries(groupedPermissions).map(([resource, perms]) => (
                <PermissionResourceGroup
                  key={resource}
                  resource={resource}
                  perms={perms}
                  selectedIds={selectedIds}
                  onTogglePerm={togglePermission}
                  onToggleGroup={toggleGroup}
                  selectAllLabel={t("form.selectAll")}
                  deselectAllLabel={t("form.deselectAll")}
                  t={t}
                />
              ))}
            </div>
          </div>
        </div>

        {/* Modal Footer */}
        <div className="flex items-center justify-end gap-3 border-t bg-muted/10 px-6 py-4">
          <Button
            type="button"
            variant="outline"
            onClick={onClose}
            disabled={isPending}
          >
            {t("form.cancel")}
          </Button>
          <Button type="submit" disabled={isSubmitDisabled}>
            {isPending ? t("form.saving") : isEditing ? t("form.save") : t("form.create")}
          </Button>
        </div>
      </form>
    </div>
  );
}

function RoleNameField({
  name,
  isSystemRole,
  isPending,
  onChange,
  label,
  placeholder,
  systemRoleHint,
}: {
  name: string;
  isSystemRole: boolean;
  isPending: boolean;
  onChange: (val: string) => void;
  label: string;
  placeholder: string;
  systemRoleHint: string;
}) {
  return (
    <div className="space-y-2">
      <Label htmlFor="role-name">{label}</Label>
      <Input
        id="role-name"
        value={name}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        disabled={isSystemRole || isPending}
        required
        className="h-10"
      />
      {isSystemRole && (
        <p className="text-xs text-muted-foreground">
          {systemRoleHint}
        </p>
      )}
    </div>
  );
}

function PermissionResourceGroup({
  resource,
  perms,
  selectedIds,
  onTogglePerm,
  onToggleGroup,
  selectAllLabel,
  deselectAllLabel,
  t,
}: {
  resource: string;
  perms: PermissionItem[];
  selectedIds: Set<number>;
  onTogglePerm: (id: number) => void;
  onToggleGroup: (perms: PermissionItem[], shouldSelectAll: boolean) => void;
  selectAllLabel: string;
  deselectAllLabel: string;
  t: ReturnType<typeof useTranslations<"roles">>;
}) {
  const allSelected = perms.every((p) => selectedIds.has(p.id));
  const resourceKey = `resources.${resource}` as Parameters<typeof t>[0];
  const resourceTitle = t.has(resourceKey) ? t(resourceKey) : resource.toUpperCase();

  return (
    <div className="space-y-2.5">
      <div className="flex items-center justify-between border-b border-border/60 pb-1.5">
        <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
          {resourceTitle}
        </span>
        <button
          type="button"
          onClick={() => onToggleGroup(perms, !allSelected)}
          className="cursor-pointer text-xs font-semibold text-primary hover:underline"
        >
          {allSelected ? deselectAllLabel : selectAllLabel}
        </button>
      </div>

      <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
        {perms.map((perm) => (
          <PermissionCheckboxItem
            key={perm.id}
            perm={perm}
            isChecked={selectedIds.has(perm.id)}
            onToggle={onTogglePerm}
            t={t}
          />
        ))}
      </div>
    </div>
  );
}

function PermissionCheckboxItem({
  perm,
  isChecked,
  onToggle,
  t,
}: {
  perm: PermissionItem;
  isChecked: boolean;
  onToggle: (id: number) => void;
  t: ReturnType<typeof useTranslations<"roles">>;
}) {
  const catalogKey = `catalog.${perm.descriptionKey}` as Parameters<typeof t>[0];
  const label = t.has(catalogKey) ? t(catalogKey) : perm.action;

  return (
    <label
      className={`flex cursor-pointer items-center gap-3 rounded-xl border p-3 text-xs transition-all ${
        isChecked
          ? "border-blue-500/50 bg-blue-50/70 text-foreground font-medium dark:bg-blue-950/40 shadow-2xs"
          : "border-border/80 bg-card text-muted-foreground hover:bg-muted/50 hover:text-foreground"
      }`}
    >
      <input
        type="checkbox"
        checked={isChecked}
        onChange={() => onToggle(perm.id)}
        className="sr-only"
      />
      <div
        className={`flex size-4.5 shrink-0 items-center justify-center rounded-md border transition-colors ${
          isChecked
            ? "border-blue-600 bg-blue-600 text-white"
            : "border-muted-foreground/40 bg-background"
        }`}
      >
        {isChecked && <Check className="size-3 stroke-[3]" />}
      </div>
      <div className="flex flex-col overflow-hidden">
        <span className="text-xs font-semibold text-foreground leading-tight">
          {label}
        </span>
        <span className="font-mono text-[10px] text-muted-foreground leading-tight mt-0.5">
          {perm.resource}:{perm.action}
        </span>
      </div>
    </label>
  );
}
