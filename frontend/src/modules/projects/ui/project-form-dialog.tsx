"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/input";
import { Label } from "@/shared/ui/label";
import { Dialog, DialogErrorAlert } from "@/shared/ui/dialog";
import { useApiErrorMessage } from "@/shared/lib/handle-api-error";
import type { Project } from "@/entities/project";
import { useCreateProject } from "../hooks/use-create-project";
import { useUpdateProject } from "../hooks/use-update-project";
import { IconProject } from "@/shared/ui/icons";

interface ProjectFormDialogProps {
  isOpen: boolean;
  onClose: () => void;
  project?: Project | null;
}

export function ProjectFormDialog({ isOpen, onClose, project }: ProjectFormDialogProps) {
  const t = useTranslations("projects");
  const getErrorMessage = useApiErrorMessage("projects");
  const createProject = useCreateProject();
  const updateProject = useUpdateProject();

  const isEditing = Boolean(project);
  const [name, setName] = useState(() => project?.name ?? "");
  const [description, setDescription] = useState(() => project?.description ?? "");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  if (!isOpen) return null;

  const isPending = createProject.isPending || updateProject.isPending;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);
    const callbacks = {
      onSuccess: () => onClose(),
      onError: (err: unknown) => setErrorMessage(getErrorMessage(err)),
    };

    if (isEditing && project) {
      updateProject.mutate({ id: project.id, data: { name, description } }, callbacks);
    } else {
      createProject.mutate({ name, description }, callbacks);
    }
  };

  return (
    <Dialog
      icon={IconProject}
      title={isEditing ? t("editProject") : t("createProject")}
      onClose={onClose}
      closeLabel={t("form.cancel")}
      disableClose={isPending}
    >
      <form onSubmit={handleSubmit} className="flex flex-col gap-4 overflow-y-auto p-6">
        {errorMessage && <DialogErrorAlert message={errorMessage} />}

        <div className="space-y-2">
          <Label htmlFor="project-name">{t("form.nameLabel")}</Label>
          <Input id="project-name" value={name} onChange={(e) => setName(e.target.value)} required className="h-10" />
        </div>

        <div className="space-y-2">
          <Label htmlFor="project-description">{t("form.descriptionLabel")}</Label>
          <Input id="project-description" value={description} onChange={(e) => setDescription(e.target.value)} className="h-10" />
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
