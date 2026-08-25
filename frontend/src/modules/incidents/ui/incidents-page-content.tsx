"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Plus, Siren } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { Label } from "@/shared/ui/label";
import { Can } from "@/entities/permission";
import { ACTIONS, RESOURCES } from "@/shared/constants/permissions";
import { useProjectsQuery } from "@/entities/project";
import { useProjectEnvironmentsQuery } from "@/entities/environment";
import { INCIDENT_STATUS, useIncidentsQuery } from "@/entities/incident";
import { IncidentStatusBadge } from "./incident-status-badge";
import { IncidentDetailPanel } from "./incident-detail-panel";
import { CreateManualIncidentDialog } from "./create-manual-incident-dialog";

function ProjectSelect({ projectId, onChange }: { projectId: string; onChange: (value: string) => void }) {
  const t = useTranslations("incidents");
  const { data: projectsPage } = useProjectsQuery();

  return (
    <div className="space-y-1.5">
      <Label htmlFor="filter-project">{t("filters.project")}</Label>
      <select
        id="filter-project"
        value={projectId}
        onChange={(event) => onChange(event.target.value)}
        className="h-9 rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
      >
        <option value="">{t("filters.allProjects")}</option>
        {projectsPage.items.map((project) => (
          <option key={project.id} value={project.id}>
            {project.name}
          </option>
        ))}
      </select>
    </div>
  );
}

function EnvironmentSelect({
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
    <div className="space-y-1.5">
      <Label htmlFor="filter-environment">{t("filters.environment")}</Label>
      <select
        id="filter-environment"
        value={environmentId}
        onChange={(event) => onChange(event.target.value)}
        className="h-9 rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
      >
        <option value="">{t("filters.allEnvironments")}</option>
        {environments.map((environment) => (
          <option key={environment.id} value={environment.id}>
            {environment.name}
          </option>
        ))}
      </select>
    </div>
  );
}

function IncidentsFilterBar({
  projectId,
  onProjectIdChange,
  environmentId,
  onEnvironmentIdChange,
  status,
  onStatusChange,
}: {
  projectId: string;
  onProjectIdChange: (value: string) => void;
  environmentId: string;
  onEnvironmentIdChange: (value: string) => void;
  status: string;
  onStatusChange: (value: string) => void;
}) {
  const t = useTranslations("incidents");

  return (
    <div className="flex flex-wrap gap-4 rounded-xl border bg-card p-4">
      <ProjectSelect projectId={projectId} onChange={onProjectIdChange} />

      {projectId && (
        <EnvironmentSelect projectId={projectId} environmentId={environmentId} onChange={onEnvironmentIdChange} />
      )}

      <div className="space-y-1.5">
        <Label htmlFor="filter-status">{t("filters.status")}</Label>
        <select
          id="filter-status"
          value={status}
          onChange={(event) => onStatusChange(event.target.value)}
          className="h-9 rounded-md border border-input bg-background px-3 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
        >
          <option value="">{t("filters.allStatuses")}</option>
          {Object.values(INCIDENT_STATUS).map((value) => (
            <option key={value} value={value}>
              {t(`status.${value}`)}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}

/**
 * Project-agnostic by default — mirrors modules/audit-log's own filter shape
 * (a flat top-level route with an optional project scope, not a required
 * one), the closest precedent for "list records optionally scoped to one
 * project" this codebase already has.
 */
export function IncidentsPageContent() {
  const t = useTranslations("incidents");
  const [projectId, setProjectId] = useState("");
  const [environmentId, setEnvironmentId] = useState("");
  const [status, setStatus] = useState("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [createOpen, setCreateOpen] = useState(false);

  const { data: incidents = [], isLoading } = useIncidentsQuery({
    projectId: projectId || undefined,
    environmentId: environmentId || undefined,
    status: status || undefined,
  });

  const selectedIncident = incidents.find((incident) => incident.id === selectedId) ?? null;

  return (
    <div className="flex flex-1 flex-col gap-6 p-6">
      <div className="flex items-start justify-between gap-4">
        <div className="flex flex-col gap-1">
          <h1 className="text-xl font-bold text-foreground">{t("title")}</h1>
          <p className="text-sm text-muted-foreground">{t("description")}</p>
        </div>
        <Can I={ACTIONS.CREATE} a={RESOURCES.INCIDENT}>
          <Button size="sm" onClick={() => setCreateOpen(true)}>
            <Plus className="mr-1.5 size-3.5" aria-hidden="true" />
            {t("create.trigger")}
          </Button>
        </Can>
      </div>

      <IncidentsFilterBar
        projectId={projectId}
        onProjectIdChange={(value) => {
          setProjectId(value);
          setEnvironmentId("");
          setSelectedId(null);
        }}
        environmentId={environmentId}
        onEnvironmentIdChange={(value) => {
          setEnvironmentId(value);
          setSelectedId(null);
        }}
        status={status}
        onStatusChange={(value) => {
          setStatus(value);
          setSelectedId(null);
        }}
      />

      <section className="flex flex-col gap-3 rounded-xl border bg-card p-5">
        <h2 className="flex items-center gap-2 text-sm font-bold text-foreground">
          <Siren className="size-4 text-primary" aria-hidden="true" /> {t("list.title")}
        </h2>

        {isLoading && <div className="h-24 w-full animate-pulse rounded-xl bg-muted/50" />}

        {!isLoading && incidents.length === 0 && <p className="text-sm text-muted-foreground">{t("empty")}</p>}

        {!isLoading && incidents.length > 0 && (
          <div className="flex flex-col divide-y">
            {incidents.map((incident) => (
              <button
                key={incident.id}
                type="button"
                onClick={() => setSelectedId(incident.id)}
                className={`flex items-center justify-between gap-3 py-3 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary ${
                  selectedId === incident.id ? "bg-muted/40" : ""
                }`}
              >
                <div className="flex min-w-0 items-center gap-3">
                  <IncidentStatusBadge status={incident.status} />
                  <span className="truncate font-medium text-foreground">{incident.title}</span>
                </div>
                <span className="shrink-0 text-xs text-muted-foreground">
                  {new Date(incident.detectedAt).toLocaleString()}
                </span>
              </button>
            ))}
          </div>
        )}
      </section>

      {selectedIncident && <IncidentDetailPanel incident={selectedIncident} />}

      {createOpen && <CreateManualIncidentDialog onClose={() => setCreateOpen(false)} />}
    </div>
  );
}
