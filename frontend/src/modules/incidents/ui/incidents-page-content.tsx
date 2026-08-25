"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Plus } from "lucide-react";
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
import { IconNotification } from "@/shared/ui/icons";

import { m } from "@/shared/lib/motion";

function ProjectSelect({ projectId, onChange }: { projectId: string; onChange: (value: string) => void }) {
  const t = useTranslations("incidents");
  const { data: projectsPage } = useProjectsQuery();

  return (
    <div className="space-y-1.5 min-w-[180px]">
      <Label htmlFor="filter-project" className="text-xs font-semibold text-muted-foreground">{t("filters.project")}</Label>
      <select
        id="filter-project"
        value={projectId}
        onChange={(event) => onChange(event.target.value)}
        className="h-9 w-full rounded-xl border border-border/60 bg-background/80 px-3 text-xs font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary shadow-2xs"
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
    <div className="space-y-1.5 min-w-[180px]">
      <Label htmlFor="filter-environment" className="text-xs font-semibold text-muted-foreground">{t("filters.environment")}</Label>
      <select
        id="filter-environment"
        value={environmentId}
        onChange={(event) => onChange(event.target.value)}
        className="h-9 w-full rounded-xl border border-border/60 bg-background/80 px-3 text-xs font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary shadow-2xs"
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
    <div className="flex flex-wrap items-center gap-4 rounded-2xl border border-border/50 bg-card/60 p-4 backdrop-blur-md shadow-2xs">
      <ProjectSelect projectId={projectId} onChange={onProjectIdChange} />

      {projectId && (
        <EnvironmentSelect projectId={projectId} environmentId={environmentId} onChange={onEnvironmentIdChange} />
      )}

      <div className="space-y-1.5 min-w-[180px]">
        <Label htmlFor="filter-status" className="text-xs font-semibold text-muted-foreground">{t("filters.status")}</Label>
        <select
          id="filter-status"
          value={status}
          onChange={(event) => onStatusChange(event.target.value)}
          className="h-9 w-full rounded-xl border border-border/60 bg-background/80 px-3 text-xs font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary shadow-2xs"
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
    <m.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="flex flex-1 flex-col gap-6"
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="flex items-center gap-2.5">
            <h1 className="text-2xl font-extrabold tracking-tight text-foreground sm:text-3xl">
              {t("title")}
            </h1>
            <span className="inline-flex items-center rounded-full border border-rose-500/30 bg-rose-500/15 px-2.5 py-0.5 font-mono text-xs font-bold text-rose-600 dark:text-rose-400">
              {incidents.length}
            </span>
          </div>
          <p className="mt-1 text-sm text-muted-foreground">{t("description")}</p>
        </div>
        <Can I={ACTIONS.CREATE} a={RESOURCES.INCIDENT}>
          <Button
            size="sm"
            onClick={() => setCreateOpen(true)}
            className="gap-2 self-start bg-gradient-to-r from-rose-600 to-red-600 font-semibold text-white shadow-md shadow-rose-500/25 hover:from-rose-700 hover:to-red-700 sm:self-auto"
          >
            <Plus className="size-4" aria-hidden="true" />
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

      <section className="flex flex-col gap-4 rounded-3xl border border-border/50 bg-card/75 p-6 backdrop-blur-xl shadow-lg shadow-black/5 dark:shadow-black/20">
        <h2 className="flex items-center gap-2.5 text-sm font-bold uppercase tracking-wider text-muted-foreground">
          <IconNotification className="size-5 shrink-0 rounded-lg shadow-2xs" /> {t("list.title")}
        </h2>

        {isLoading && <div className="h-28 w-full animate-pulse rounded-2xl bg-muted/50" />}

        {!isLoading && incidents.length === 0 && (
          <div className="flex flex-col items-center justify-center py-12 text-center">
            <p className="text-sm font-medium text-muted-foreground">{t("empty")}</p>
          </div>
        )}

        {!isLoading && incidents.length > 0 && (
          <div className="max-h-96 overflow-y-auto flex flex-col divide-y divide-border/40 pr-1">
            {incidents.map((incident) => (
              <button
                key={incident.id}
                type="button"
                onClick={() => setSelectedId(incident.id)}
                className={`flex items-center justify-between gap-4 rounded-xl px-4 py-3.5 text-left transition-all duration-200 cursor-pointer ${
                  selectedId === incident.id
                    ? "bg-primary/10 border border-primary/20 shadow-xs"
                    : "hover:bg-muted/40"
                }`}
              >
                <div className="flex min-w-0 items-center gap-3">
                  <IncidentStatusBadge status={incident.status} />
                  <span className="truncate font-semibold text-sm text-foreground">{incident.title}</span>
                </div>
                <span className="shrink-0 font-mono text-xs text-muted-foreground">
                  {new Date(incident.detectedAt).toLocaleString()}
                </span>
              </button>
            ))}
          </div>
        )}
      </section>

      {selectedIncident && <IncidentDetailPanel incident={selectedIncident} />}

      {createOpen && <CreateManualIncidentDialog onClose={() => setCreateOpen(false)} />}
    </m.div>
  );
}
