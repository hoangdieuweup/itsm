"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/input";
import { Label } from "@/shared/ui/label";
import { Dialog, DialogErrorAlert } from "@/shared/ui/dialog";
import { useApiErrorMessage } from "@/shared/lib/handle-api-error";
import { ENVIRONMENT_TYPE, type Environment, type EnvironmentType } from "@/entities/environment";
import { useCreateEnvironment } from "../hooks/use-create-environment";
import { useUpdateEnvironment } from "../hooks/use-update-environment";
import { IconServer } from "@/shared/ui/icons";

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
  const [type, setType] = useState<EnvironmentType>(environment?.type ?? ENVIRONMENT_TYPE.DEV);
  const [name, setName] = useState(() => environment?.name ?? "");
  const [baseUrl, setBaseUrl] = useState(() => environment?.baseUrl ?? "");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  if (!isOpen) return null;

  const isPending = createEnvironment.isPending || updateEnvironment.isPending;
  const availableTypes = Object.values(ENVIRONMENT_TYPE).filter(
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
    <Dialog
      icon={IconServer}
      title={isEditing ? t("editEnvironment") : t("createEnvironment")}
      onClose={onClose}
      closeLabel={t("form.cancel")}
      disableClose={isPending}
    >
      <form onSubmit={handleSubmit} className="flex flex-col gap-4 overflow-y-auto p-6">
        {errorMessage && <DialogErrorAlert message={errorMessage} />}

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
    </Dialog>
  );
}
