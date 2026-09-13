"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/input";
import { Label } from "@/shared/ui/label";
import { Dialog, DialogErrorAlert } from "@/shared/ui/dialog";
import { useApiErrorMessage } from "@/shared/lib/handle-api-error";
import { PROJECT_LINK_TYPE, type ProjectLink, type ProjectLinkType } from "../model/schema";
import { useCreateProjectLink } from "../hooks/use-create-project-link";
import { useUpdateProjectLink } from "../hooks/use-update-project-link";
import { IconProject } from "@/shared/ui/icons";

interface ProjectLinkFormDialogProps {
  isOpen: boolean;
  onClose: () => void;
  projectId: string;
  link?: ProjectLink | null;
}

export function ProjectLinkFormDialog({ isOpen, onClose, projectId, link }: ProjectLinkFormDialogProps) {
  const t = useTranslations("projects");
  const getErrorMessage = useApiErrorMessage("projects");
  const createLink = useCreateProjectLink(projectId);
  const updateLink = useUpdateProjectLink(projectId);

  const isEditing = Boolean(link);
  const [type, setType] = useState<ProjectLinkType>(link?.type ?? PROJECT_LINK_TYPE.OTHER);
  const [name, setName] = useState(() => link?.name ?? "");
  const [url, setUrl] = useState(() => link?.url ?? "");
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  if (!isOpen) return null;

  const isPending = createLink.isPending || updateLink.isPending;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);
    const callbacks = {
      onSuccess: () => onClose(),
      onError: (err: unknown) => setErrorMessage(getErrorMessage(err)),
    };

    if (isEditing && link) {
      updateLink.mutate({ id: link.id, data: { name, url } }, callbacks);
    } else {
      createLink.mutate({ type, name, url }, callbacks);
    }
  };

  return (
    <Dialog
      icon={IconProject}
      title={isEditing ? t("editLink") : t("createLink")}
      onClose={onClose}
      closeLabel={t("form.cancel")}
      disableClose={isPending}
    >
      <form onSubmit={handleSubmit} className="flex flex-col gap-4 overflow-y-auto p-6">
        {errorMessage && <DialogErrorAlert message={errorMessage} />}

        <div className="space-y-2">
          <Label htmlFor="link-type">{t("form.linkTypeLabel")}</Label>
          <select
            id="link-type"
            value={type}
            onChange={(e) => setType(e.target.value as ProjectLinkType)}
            disabled={isEditing}
            className="h-10 w-full rounded-md border bg-background px-3 text-sm disabled:opacity-60"
          >
            <option value="jira">{t("linkTypes.jira")}</option>
            <option value="git">{t("linkTypes.git")}</option>
            <option value="other">{t("linkTypes.other")}</option>
          </select>
        </div>

        <div className="space-y-2">
          <Label htmlFor="link-name">{t("form.nameLabel")}</Label>
          <Input id="link-name" value={name} onChange={(e) => setName(e.target.value)} required className="h-10" />
        </div>

        <div className="space-y-2">
          <Label htmlFor="link-url">{t("form.urlLabel")}</Label>
          <Input id="link-url" value={url} onChange={(e) => setUrl(e.target.value)} required className="h-10" />
        </div>

        <div className="mt-2 flex items-center justify-end gap-3">
          <Button type="button" variant="outline" onClick={onClose} disabled={isPending}>
            {t("form.cancel")}
          </Button>
          <Button type="submit" disabled={isPending || !name.trim() || !url.trim()}>
            {isPending ? t("form.saving") : isEditing ? t("form.save") : t("form.create")}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
