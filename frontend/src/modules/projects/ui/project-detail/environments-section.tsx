"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Plus } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { ConfirmDialog } from "@/shared/ui/confirm-dialog";
import { CanInProject } from "@/entities/permission";
import { ACTIONS, RESOURCES } from "@/shared/constants/permissions";
import { useProjectEnvironmentsQuery, type Environment } from "@/entities/environment";
import { IconServer } from "@/shared/ui/icons";
import { m } from "@/shared/lib/motion";
import { useDeleteEnvironment } from "../../hooks/use-delete-environment";
import { EnvironmentFormDialog } from "../environment-form-dialog";
import { EnvironmentCard } from "./environment-card";
import { itemVariants } from "./motion-variants";

export function EnvironmentsSection({
  projectId,
  onManageTunnels,
  onManageLoki,
  onManageAlerting,
}: {
  projectId: string;
  onManageTunnels: (environment: Environment) => void;
  onManageLoki: (environment: Environment) => void;
  onManageAlerting: (environment: Environment) => void;
}) {
  const t = useTranslations("projects");
  const { data: environments } = useProjectEnvironmentsQuery(projectId);
  const deleteEnvironment = useDeleteEnvironment(projectId);

  const [envFormTarget, setEnvFormTarget] = useState<Environment | "create" | null>(null);
  const [envDeleteTarget, setEnvDeleteTarget] = useState<Environment | null>(null);

  return (
    <>
      <m.section variants={itemVariants} className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <IconServer className="size-5 shrink-0 rounded-lg shadow-2xs" />
            <h2 className="text-sm font-bold uppercase tracking-wider text-muted-foreground">
              {t("sections.environments")} ({environments.length})
            </h2>
          </div>
          <CanInProject I={ACTIONS.CREATE} a={RESOURCES.ENVIRONMENT}>
            <Button
              size="sm"
              onClick={() => setEnvFormTarget("create")}
              className="gap-1.5 bg-gradient-to-r from-emerald-600 to-teal-600 font-semibold text-white shadow-xs hover:from-emerald-700 hover:to-teal-700"
            >
              <Plus className="size-3.5" /> {t("actions.addEnvironment")}
            </Button>
          </CanInProject>
        </div>

        {environments.length === 0 ? (
          <div className="flex flex-col items-center justify-center rounded-3xl border border-border/50 bg-card/60 py-12 text-center backdrop-blur-md">
            <p className="text-sm text-muted-foreground">{t("empty.environments")}</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {environments.map((env) => (
              <EnvironmentCard
                key={env.id}
                env={env}
                onManageTunnels={onManageTunnels}
                onManageLoki={onManageLoki}
                onManageAlerting={onManageAlerting}
                onEdit={setEnvFormTarget}
                onDelete={setEnvDeleteTarget}
              />
            ))}
          </div>
        )}
      </m.section>

      {envFormTarget !== null && (
        <EnvironmentFormDialog
          isOpen
          onClose={() => setEnvFormTarget(null)}
          projectId={projectId}
          environment={envFormTarget === "create" ? null : envFormTarget}
          existingTypes={environments.map((e) => e.type)}
        />
      )}
      <ConfirmDialog
        isOpen={envDeleteTarget !== null}
        onClose={() => setEnvDeleteTarget(null)}
        onConfirm={() => {
          if (envDeleteTarget) {
            deleteEnvironment.mutate(envDeleteTarget.id, { onSuccess: () => setEnvDeleteTarget(null) });
          }
        }}
        title={t("deleteConfirm.environmentTitle")}
        description={t("deleteConfirm.environmentDescription", { name: envDeleteTarget?.name ?? "" })}
        isLoading={deleteEnvironment.isPending}
      />
    </>
  );
}

export function EnvironmentsSectionNoPermission() {
  const t = useTranslations("projects");
  return (
    <m.section variants={itemVariants} className="space-y-4">
      <div className="flex items-center gap-2.5">
        <IconServer className="size-5 shrink-0 rounded-lg shadow-2xs" />
        <h2 className="text-sm font-bold uppercase tracking-wider text-muted-foreground">
          {t("sections.environments")}
        </h2>
      </div>
      <div className="flex flex-col items-center justify-center rounded-3xl border border-border/50 bg-card/60 py-12 text-center backdrop-blur-md">
        <p className="text-sm text-muted-foreground">{t("noPermission.environments")}</p>
      </div>
    </m.section>
  );
}
