"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Siren } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/input";
import { Label } from "@/shared/ui/label";
import { Dialog, DialogErrorAlert } from "@/shared/ui/dialog";
import { useApiErrorMessage } from "@/shared/lib/handle-api-error";
import { useProjectsQuery } from "@/entities/project";
import { useProjectEnvironmentsQuery } from "@/entities/environment";
import { ALERT_SEVERITY, INCIDENT_CATEGORY } from "@/entities/incident";
import { useCreateManualIncident } from "../hooks/use-create-manual-incident";

/** useProjectEnvironmentsQuery is a Suspense query with no built-in
 * "disabled" mode — this is only ever mounted once a project is picked,
 * mirroring how IncidentsFilterBar's own EnvironmentSelect is gated. */
function EnvironmentPicker({
  projectId,
  environmentId,
  onChange,
}: {
  projectId: string;
  environmentId: string;
  onChange: (value: string) => void;
}) {
  const t = useTranslations("incidents");
  const { data: environments } = useProjectEnvironmentsQuery(projectId);
  return (
    <select
      id="create-incident-environment"
      value={environmentId}
      onChange={(event) => onChange(event.target.value)}
      required
      className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
    >
      <option value="" disabled>
        {t("create.selectEnvironment")}
      </option>
      {environments.map((environment) => (
        <option key={environment.id} value={environment.id}>
          {environment.name}
        </option>
      ))}
    </select>
  );
}

export function CreateManualIncidentDialog({ onClose }: { onClose: () => void }) {
  const t = useTranslations("incidents");
  const getErrorMessage = useApiErrorMessage("incidents");
  const { data: projectsPage } = useProjectsQuery();

  const [projectId, setProjectId] = useState("");
  const [environmentId, setEnvironmentId] = useState("");
  const [title, setTitle] = useState("");
  const [severity, setSeverity] = useState<string>(ALERT_SEVERITY.MEDIUM);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const createIncident = useCreateManualIncident();

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    setErrorMessage(null);
    createIncident.mutate(
      { environmentId, category: INCIDENT_CATEGORY.MANUAL, severity, title },
      { onSuccess: onClose, onError: (err) => setErrorMessage(getErrorMessage(err)) },
    );
  };

  return (
    <Dialog
      icon={Siren}
      title={t("create.title")}
      onClose={onClose}
      closeLabel={t("create.cancel")}
    >
      <form onSubmit={handleSubmit} className="space-y-4 overflow-y-auto p-6">
        {errorMessage && <DialogErrorAlert message={errorMessage} />}

        <div className="space-y-1.5">
          <Label htmlFor="create-incident-project">{t("filters.project")}</Label>
          <select
            id="create-incident-project"
            value={projectId}
            onChange={(event) => {
              setProjectId(event.target.value);
              setEnvironmentId("");
            }}
            required
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          >
            <option value="" disabled>
              {t("create.selectProject")}
            </option>
            {projectsPage.items.map((project) => (
              <option key={project.id} value={project.id}>
                {project.name}
              </option>
            ))}
          </select>
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="create-incident-environment">{t("filters.environment")}</Label>
          {projectId ? (
            <EnvironmentPicker projectId={projectId} environmentId={environmentId} onChange={setEnvironmentId} />
          ) : (
            <select
              id="create-incident-environment"
              disabled
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-50"
            >
              <option>{t("create.selectProjectFirst")}</option>
            </select>
          )}
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="create-incident-title">{t("create.titleLabel")}</Label>
          <Input
            id="create-incident-title"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            required
          />
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="create-incident-severity">{t("create.severityLabel")}</Label>
          <select
            id="create-incident-severity"
            value={severity}
            onChange={(event) => setSeverity(event.target.value)}
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          >
            {Object.values(ALERT_SEVERITY).map((value) => (
              <option key={value} value={value}>
                {t(`severities.${value}`)}
              </option>
            ))}
          </select>
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="outline" onClick={onClose}>
            {t("create.cancel")}
          </Button>
          <Button type="submit" disabled={createIncident.isPending}>
            {createIncident.isPending ? t("create.creating") : t("create.create")}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
