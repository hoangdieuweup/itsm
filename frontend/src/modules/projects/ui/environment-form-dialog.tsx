"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { X, Server } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/input";
import { Label } from "@/shared/ui/label";
import { useApiErrorMessage } from "@/shared/lib/handle-api-error";
import { ENVIRONMENT_TYPES, type Environment, type EnvironmentType } from "@/entities/environment";
import { useCreateEnvironment } from "../hooks/use-create-environment";
import { useUpdateEnvironment } from "../hooks/use-update-environment";

interface EnvironmentFormDialogProps {
  isOpen: boolean;
  onClose: () => void;
  projectId: string;
  environment?: Environment | null;
  existingTypes: EnvironmentType[];
}

export function EnvironmentFormDialog({
  isOpen,
  onClose,
  projectId,
  environment,
  existingTypes,
}: EnvironmentFormDialogProps) {
  const t = useTranslations("projects");
  const getErrorMessage = useApiErrorMessage("projects");
  const createEnvironment = useCreateEnvironment(projectId);
  const updateEnvironment = useUpdateEnvironment(projectId);

  const isEditing = Boolean(environment);
  const [type, setType] = useState<EnvironmentType>(environment?.type ?? "dev");
  const [name, setName] = useState(() => environment?.name ?? "");
  const [baseUrl, setBaseUrl] = useState(() => environment?.baseUrl ?? "");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  if (!isOpen) return null;

  const isPending = createEnvironment.isPending || updateEnvironment.isPending;
  const availableTypes = ENVIRONMENT_TYPES.filter(
    (envType) => envType === environment?.type || !existingTypes.includes(envType),
  );

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);
    const callbacks = {
      onSuccess: () => onClose(),
      onError: (err: unknown) => setErrorMessage(getErrorMessage(err)),
    };

    if (isEditing && environment) {
      updateEnvironment.mutate({ id: environment.id, data: { name, baseUrl } }, callbacks);
    } else {
      createEnvironment.mutate({ type, name, baseUrl }, callbacks);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-xs animate-in fade-in-0" role="dialog" aria-modal="true">
      <div className="flex w-full max-w-md flex-col rounded-2xl border bg-card shadow-2xl animate-in zoom-in-95">
        <div className="flex items-center justify-between border-b px-6 py-4">
          <div className="flex items-center gap-2.5">
            <div className="flex size-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <Server className="size-4" />
            </div>
            <h2 className="text-lg font-bold text-foreground">
              {isEditing ? t("editEnvironment") : t("createEnvironment")}
            </h2>
          </div>
          <button type="button" onClick={onClose} className="cursor-pointer rounded-lg p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground">
            <X className="size-5" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4 p-6">
          {errorMessage && (
            <div role="alert" className="rounded-lg border border-destructive/20 bg-destructive/10 p-3 text-sm text-destructive">
              {errorMessage}
            </div>
          )}

          <div className="space-y-2">
            <Label htmlFor="env-type">{t("form.typeLabel")}</Label>
            <select
              id="env-type"
              value={type}
              onChange={(e) => setType(e.target.value as EnvironmentType)}
              disabled={isEditing}
              className="h-10 w-full rounded-md border bg-background px-3 text-sm disabled:opacity-60"
            >
              {availableTypes.map((envType) => (
                <option key={envType} value={envType}>
                  {t(`environmentTypes.${envType}`)}
                </option>
              ))}
            </select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="env-name">{t("form.nameLabel")}</Label>
            <Input id="env-name" value={name} onChange={(e) => setName(e.target.value)} required className="h-10" />
          </div>

          <div className="space-y-2">
            <Label htmlFor="env-base-url">{t("form.baseUrlLabel")}</Label>
            <Input id="env-base-url" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} className="h-10" />
          </div>

          <div className="mt-2 flex items-center justify-end gap-3">
            <Button type="button" variant="outline" onClick={onClose} disabled={isPending}>
              {t("form.cancel")}
            </Button>
            <Button type="submit" disabled={isPending || !name.trim()}>
              {isPending ? t("form.saving") : isEditing ? t("form.save") : t("form.create")}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
