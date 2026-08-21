"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { X, FolderKanban } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/input";
import { Label } from "@/shared/ui/label";
import { useApiErrorMessage } from "@/shared/lib/handle-api-error";
import type { Project } from "@/entities/project";
import { useCreateProject } from "../hooks/use-create-project";
import { useUpdateProject } from "../hooks/use-update-project";

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
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-xs animate-in fade-in-0"
      role="dialog"
      aria-modal="true"
    >
      <div className="flex w-full max-w-md flex-col rounded-2xl border bg-card shadow-2xl animate-in zoom-in-95">
        <div className="flex items-center justify-between border-b px-6 py-4">
          <div className="flex items-center gap-2.5">
            <div className="flex size-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <FolderKanban className="size-4" />
            </div>
            <h2 className="text-lg font-bold text-foreground">
              {isEditing ? t("editProject") : t("createProject")}
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
      </div>
    </div>
  );
}
