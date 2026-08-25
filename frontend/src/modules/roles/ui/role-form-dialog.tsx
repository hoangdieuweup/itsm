"use client";

import { useState, useMemo } from "react";
import { useTranslations } from "next-intl";
import { Check } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/input";
import { Label } from "@/shared/ui/label";
import { Dialog, DialogErrorAlert } from "@/shared/ui/dialog";
import { useApiErrorMessage } from "@/shared/lib/handle-api-error";
import {
  usePermissions,
  isProtectedAdminRole,
  type Role,
  type PermissionItem,
} from "@/entities/role";
import { useCreateRole } from "../hooks/use-create-role";
import { useUpdateRole } from "../hooks/use-update-role";
import { IconPermission } from "@/shared/ui/icons";

interface RoleFormDialogProps {
  isOpen: boolean;
  onClose: () => void;
  role?: Role | null;
}

export function RoleFormDialog({ isOpen, onClose, role }: RoleFormDialogProps) {
  if (!isOpen) return null;

  return <RoleFormInner key={role ? `edit-${role.id}` : "create-new"} role={role} onClose={onClose} />;
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
  const isAdminRole = isProtectedAdminRole(role);

  const [name, setName] = useState(() => role?.name ?? "");
  const [selectedIds, setSelectedIds] = useState<Set<string>>(
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

  const togglePermission = (id: string) => {
    if (isAdminRole) return;
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleGroup = (perms: PermissionItem[], shouldSelectAll: boolean) => {
    if (isAdminRole) return;
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
    if (isAdminRole) {
      onClose();
      return;
    }
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
    <Dialog
      icon={IconPermission}
      title={
        isAdminRole
          ? `${t("actions.view")} - ${role?.name}`
          : isEditing
            ? t("editRole")
            : t("createRole")
      }
      onClose={onClose}
      closeLabel={t("form.cancel")}
      size="xl"
    >
      {/* Modal Body / Form */}
      <form
        onSubmit={handleSubmit}
        className="flex flex-1 min-h-0 flex-col overflow-hidden h-[min(620px,70vh)]"
      >
        <div className="flex-1 min-h-0 space-y-6 overflow-y-auto px-7 sm:px-8 py-5">
          {errorMessage && <DialogErrorAlert message={errorMessage} />}

          {isAdminRole && (
            <div className="flex items-start gap-2.5 rounded-2xl border border-amber-500/20 bg-amber-500/10 p-4 text-xs text-amber-900 dark:text-amber-200">
              <IconPermission className="size-5 shrink-0 mt-0.5" />
              <div>
                <span className="font-semibold">{t("badges.adminProtected")}:</span>{" "}
                {t("form.adminProtectedAlert")}
              </div>
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

          {/* Permissions List - Clean layout without rigid outer boxes */}
          <div className="space-y-4">
            <Label className="text-sm font-bold text-foreground">
              {t("form.permissionsLabel")}
            </Label>
            <div className="space-y-6">
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
                  isDisabled={isAdminRole}
                  t={t}
                />
              ))}
            </div>
          </div>
        </div>

        {/* Modal Footer - Pinned nicely at bottom */}
        <div className="flex shrink-0 items-center justify-end gap-3 border-t border-border/30 bg-card/80 px-7 sm:px-8 py-4 backdrop-blur-md">
          {isAdminRole ? (
            <Button type="button" onClick={onClose} className="rounded-xl">
              {t("form.cancel")}
            </Button>
          ) : (
            <>
              <Button
                type="button"
                variant="outline"
                onClick={onClose}
                disabled={isPending}
                className="rounded-xl font-medium"
              >
                {t("form.cancel")}
              </Button>
              <Button
                type="submit"
                disabled={isSubmitDisabled}
                className="rounded-xl bg-blue-600 font-semibold text-white hover:bg-blue-700 dark:bg-blue-600 dark:hover:bg-blue-700 shadow-xs cursor-pointer"
              >
                {isPending
                  ? t("form.saving")
                  : isEditing
                    ? t("form.save")
                    : t("form.create")}
              </Button>
            </>
          )}
        </div>
      </form>
    </Dialog>
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
      <Label htmlFor="role-name" className="text-sm font-semibold">{label}</Label>
      <Input
        id="role-name"
        value={name}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        disabled={isSystemRole || isPending}
        required
        className="h-11 rounded-2xl border-border/40 bg-muted/20 px-4 text-sm transition-colors focus:bg-background"
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
  isDisabled,
  t,
}: {
  resource: string;
  perms: PermissionItem[];
  selectedIds: Set<string>;
  onTogglePerm: (id: string) => void;
  onToggleGroup: (perms: PermissionItem[], shouldSelectAll: boolean) => void;
  selectAllLabel: string;
  deselectAllLabel: string;
  isDisabled: boolean;
  t: ReturnType<typeof useTranslations<"roles">>;
}) {
  const allSelected = perms.every((p) => selectedIds.has(p.id));
  const resourceKey = `resources.${resource}` as Parameters<typeof t>[0];
  const resourceTitle = t.has(resourceKey) ? t(resourceKey) : resource.toUpperCase();

  return (
    <div className="space-y-2.5">
      {/* Group Header - Clean without divider line */}
      <div className="flex items-center justify-between pt-1">
        <span className="text-xs font-bold uppercase tracking-wider text-muted-foreground">
          {resourceTitle}
        </span>
        {!isDisabled && (
          <button
            type="button"
            onClick={() => onToggleGroup(perms, !allSelected)}
            className="cursor-pointer text-xs font-semibold text-blue-600 hover:text-blue-700 dark:text-blue-400 hover:underline"
          >
            {allSelected ? deselectAllLabel : selectAllLabel}
          </button>
        )}
      </div>

      <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
        {perms.map((perm) => (
          <PermissionCheckboxItem
            key={perm.id}
            perm={perm}
            isChecked={selectedIds.has(perm.id)}
            onToggle={onTogglePerm}
            isDisabled={isDisabled}
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
  isDisabled,
  t,
}: {
  perm: PermissionItem;
  isChecked: boolean;
  onToggle: (id: string) => void;
  isDisabled: boolean;
  t: ReturnType<typeof useTranslations<"roles">>;
}) {
  const catalogKey = `catalog.${perm.descriptionKey}` as Parameters<typeof t>[0];
  const label = t.has(catalogKey) ? t(catalogKey) : perm.action;

  return (
    <button
      type="button"
      role="checkbox"
      aria-checked={isChecked}
      disabled={isDisabled}
      onClick={() => onToggle(perm.id)}
      className={`flex w-full text-left items-center gap-3 rounded-2xl border p-3.5 text-xs transition-all select-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/40 ${
        isDisabled ? "cursor-default opacity-85" : "cursor-pointer"
      } ${
        isChecked
          ? "border-blue-500/40 bg-blue-500/10 text-foreground font-medium dark:border-blue-500/30 dark:bg-blue-500/15 shadow-2xs"
          : "border-border/40 bg-card/60 text-muted-foreground hover:border-border/70 hover:bg-muted/40 hover:text-foreground"
      }`}
    >
      <div
        className={`flex size-5 shrink-0 items-center justify-center rounded-lg border transition-colors ${
          isChecked
            ? "border-blue-600 bg-blue-600 text-white dark:border-blue-500 dark:bg-blue-500 shadow-2xs"
            : "border-muted-foreground/30 bg-background"
        }`}
      >
        {isChecked && <Check className="size-3 stroke-[3]" />}
      </div>
      <div className="flex flex-col overflow-hidden">
        <span className="text-xs font-bold text-foreground leading-tight">
          {label}
        </span>
        <span className="font-mono text-[10px] text-muted-foreground leading-tight mt-0.5">
          {perm.resource}:{perm.action}
        </span>
      </div>
    </button>
  );
}
