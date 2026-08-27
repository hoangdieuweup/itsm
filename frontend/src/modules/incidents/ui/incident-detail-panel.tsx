"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { CheckCircle2, Eye } from "lucide-react";
import { formatDatetime } from "@/shared/lib/datetime";
import { Button } from "@/shared/ui/button";
import { ConfirmDialog } from "@/shared/ui/confirm-dialog";
import { CanInProject, ProjectPermissionProvider } from "@/entities/permission";
import { ACTIONS, PERMISSIONS } from "@/shared/constants/permissions";
import { useApiErrorMessage } from "@/shared/lib/handle-api-error";
import { INCIDENT_STATUS, type Incident } from "@/entities/incident";
import { useAcknowledgeIncident } from "../hooks/use-acknowledge-incident";
import { useResolveIncident } from "../hooks/use-resolve-incident";
import { IncidentStatusBadge } from "./incident-status-badge";

export function IncidentDetailPanel({ incident }: { incident: Incident }) {
  const t = useTranslations("incidents");
  const getErrorMessage = useApiErrorMessage("incidents");
  const acknowledge = useAcknowledgeIncident();
  const resolve = useResolveIncident();
  const [resolveConfirmOpen, setResolveConfirmOpen] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const isResolved = incident.status === INCIDENT_STATUS.RESOLVED;
  const canAcknowledge = incident.status === INCIDENT_STATUS.OPEN;

  return (
    <ProjectPermissionProvider projectId={incident.projectId}>
      <section className="flex flex-col gap-4 rounded-xl border bg-card p-5">
        {errorMessage && (
          <div role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {errorMessage}
          </div>
        )}

        <div className="flex items-start justify-between gap-4">
          <div className="flex flex-col gap-1.5">
            <div className="flex items-center gap-2">
              <IncidentStatusBadge status={incident.status} />
              <span className="text-xs font-semibold uppercase text-muted-foreground">
                {t(`severities.${incident.severity}`)}
              </span>
            </div>
            <h2 className="text-base font-bold text-foreground">{incident.title}</h2>
            <p className="text-xs text-muted-foreground">
              {t("detail.detected")} {formatDatetime(incident.detectedAt)}
            </p>
          </div>

          <div className="flex shrink-0 gap-2">
            <CanInProject I={ACTIONS.ACKNOWLEDGE} a={PERMISSIONS.PROJECT_INCIDENT.RESOURCE}>
              <Button
                variant="outline"
                size="sm"
                disabled={!canAcknowledge || acknowledge.isPending}
                onClick={() => {
                  setErrorMessage(null);
                  acknowledge.mutate(incident.id, {
                    onError: (err) => setErrorMessage(getErrorMessage(err)),
                  });
                }}
              >
                <Eye className="mr-1.5 size-3.5" aria-hidden="true" />
                {t("detail.acknowledge")}
              </Button>
            </CanInProject>
            <CanInProject I={ACTIONS.RESOLVE} a={PERMISSIONS.PROJECT_INCIDENT.RESOURCE}>
              <Button
                variant="default"
                size="sm"
                disabled={isResolved || resolve.isPending}
                onClick={() => {
                  setErrorMessage(null);
                  setResolveConfirmOpen(true);
                }}
              >
                <CheckCircle2 className="mr-1.5 size-3.5" aria-hidden="true" />
                {t("detail.resolve")}
              </Button>
            </CanInProject>
          </div>
        </div>

        <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm sm:grid-cols-3">
          <div>
            <dt className="text-xs uppercase text-muted-foreground">{t("detail.category")}</dt>
            <dd className="text-foreground">{t(`categories.${incident.category}`)}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase text-muted-foreground">{t("detail.source")}</dt>
            <dd className="text-foreground">{t(`sources.${incident.source}`)}</dd>
          </div>
          {incident.acknowledgedAt && (
            <div>
              <dt className="text-xs uppercase text-muted-foreground">{t("detail.acknowledgedAt")}</dt>
              <dd className="text-foreground">{formatDatetime(incident.acknowledgedAt)}</dd>
            </div>
          )}
          {incident.resolvedAt && (
            <div>
              <dt className="text-xs uppercase text-muted-foreground">{t("detail.resolvedAt")}</dt>
              <dd className="text-foreground">{formatDatetime(incident.resolvedAt)}</dd>
            </div>
          )}
        </dl>

        <ConfirmDialog
          isOpen={resolveConfirmOpen}
          onClose={() => setResolveConfirmOpen(false)}
          onConfirm={() =>
            resolve.mutate(incident.id, {
              onSuccess: () => setResolveConfirmOpen(false),
              onError: (err) => setErrorMessage(getErrorMessage(err)),
            })
          }
          title={t("detail.resolveConfirm.title")}
          description={t("detail.resolveConfirm.description", { title: incident.title })}
          confirmText={t("detail.resolve")}
          variant="default"
          isLoading={resolve.isPending}
        />
      </section>
    </ProjectPermissionProvider>
  );
}
