"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { X, Link2 } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/input";
import { Label } from "@/shared/ui/label";
import { useApiErrorMessage } from "@/shared/lib/handle-api-error";
import type { ProjectLink } from "../api/fetchers";
import { useCreateProjectLink } from "../hooks/use-create-project-link";
import { useUpdateProjectLink } from "../hooks/use-update-project-link";

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
  const [type, setType] = useState<"jira" | "git" | "other">(link?.type ?? "other");
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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-xs animate-in fade-in-0" role="dialog" aria-modal="true">
      <div className="flex w-full max-w-md flex-col rounded-2xl border bg-card shadow-2xl animate-in zoom-in-95">
        <div className="flex items-center justify-between border-b px-6 py-4">
          <div className="flex items-center gap-2.5">
            <div className="flex size-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <Link2 className="size-4" />
            </div>
            <h2 className="text-lg font-bold text-foreground">
              {isEditing ? t("editLink") : t("createLink")}
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
            <Label htmlFor="link-type">{t("form.linkTypeLabel")}</Label>
            <select
              id="link-type"
              value={type}
              onChange={(e) => setType(e.target.value as "jira" | "git" | "other")}
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
      </div>
    </div>
  );
}
