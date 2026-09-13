"use client";

import { useTranslations } from "next-intl";
import { Pencil, Trash2, ScrollText } from "lucide-react";
import { Link } from "@/shared/lib/i18n/navigation";
import { CanInProject, CanInProjectOrAccount } from "@/entities/permission";
import { ACTIONS, RESOURCES } from "@/shared/constants/permissions";
import { type Environment } from "@/entities/environment";
import { useLokiConfigQuery } from "@/entities/loki-config";
import { useCloudflareConfigQuery } from "@/entities/cloudflare-config";
import { IconDns, IconNotification, IconGrafana } from "@/shared/ui/icons";
import { m } from "@/shared/lib/motion";

export function EnvironmentCard({
  env,
  onManageTunnels,
  onManageLoki,
  onManageAlerting,
  onEdit,
  onDelete,
}: {
  env: Environment;
  onManageTunnels: (environment: Environment) => void;
  onManageLoki: (environment: Environment) => void;
  onManageAlerting: (environment: Environment) => void;
  onEdit: (environment: Environment) => void;
  onDelete: (environment: Environment) => void;
}) {
  const t = useTranslations("projects");
  const { data: lokiConfig } = useLokiConfigQuery(env.id);
  const { data: cloudflareConfig } = useCloudflareConfigQuery(env.id);
  const hasLogsToView = Boolean(lokiConfig) || Boolean(cloudflareConfig);

  return (
    <m.div
      whileHover={{ y: -3, scale: 1.01 }}
      transition={{ duration: 0.2 }}
      className="group relative flex flex-col justify-between rounded-2xl border border-border/60 bg-card/80 p-5 backdrop-blur-xl transition-all duration-300 hover:border-emerald-500/40 hover:shadow-lg hover:shadow-emerald-500/5"
    >
      <div>
        {/* Env Top Header */}
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-500/30 bg-emerald-500/15 px-2.5 py-1 text-xs font-bold text-emerald-600 dark:text-emerald-400 uppercase tracking-wider">
              <span className="relative flex size-2">
                <span className="absolute inline-flex size-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                <span className="relative inline-flex size-2 rounded-full bg-emerald-500" />
              </span>
              {t(`environmentTypes.${env.type}`)}
            </span>
            <h3 className="font-bold text-sm text-foreground truncate">{env.name}</h3>
          </div>

          <div className="flex items-center gap-1">
            {hasLogsToView && (
              <CanInProject I={ACTIONS.READ} a={RESOURCES.PROJECT_LOKI_CONFIG}>
                <Link
                  href={`/admin/projects/${env.projectId}/environments/${env.id}/logs`}
                  className="flex size-7 items-center justify-center rounded-lg text-muted-foreground hover:bg-muted hover:text-foreground cursor-pointer"
                  title={t("actions.manageLogs")}
                >
                  <ScrollText className="size-3.5" />
                </Link>
              </CanInProject>
            )}
            <CanInProject I={ACTIONS.UPDATE} a={RESOURCES.ENVIRONMENT}>
              <button
                type="button"
                onClick={() => onEdit(env)}
                className="flex size-7 items-center justify-center rounded-lg text-muted-foreground hover:bg-muted hover:text-foreground cursor-pointer"
                title={t("actions.edit")}
              >
                <Pencil className="size-3.5" />
              </button>
            </CanInProject>
            <CanInProject I={ACTIONS.DELETE} a={RESOURCES.ENVIRONMENT}>
              <button
                type="button"
                onClick={() => onDelete(env)}
                className="flex size-7 items-center justify-center rounded-lg text-rose-600 hover:bg-rose-500/10 hover:text-rose-700 dark:hover:bg-rose-950/50 cursor-pointer"
                title={t("actions.delete")}
              >
                <Trash2 className="size-3.5" />
              </button>
            </CanInProject>
          </div>
        </div>

        {/* High-Tech Operations Launch Buttons */}
        <div className="mt-5 grid grid-cols-3 gap-2">
          <CanInProjectOrAccount I={ACTIONS.READ} a={RESOURCES.PROJECT_CLOUDFLARE_TUNNEL}>
            <button
              type="button"
              onClick={() => onManageTunnels(env)}
              className="group/btn flex flex-col items-center justify-center gap-1.5 rounded-xl border border-blue-500/20 bg-blue-500/5 p-2.5 text-center transition-all hover:border-blue-500/40 hover:bg-blue-500/15 cursor-pointer"
              title={t("actions.manageTunnels")}
            >
              <IconDns className="size-4.5 group-hover/btn:scale-110 transition-transform" />
              <span className="text-[10px] font-bold text-blue-700 dark:text-blue-300 uppercase tracking-tight">
                {t("edgeDns")}
              </span>
            </button>
          </CanInProjectOrAccount>

          <CanInProject I={ACTIONS.READ} a={RESOURCES.PROJECT_LOKI_CONFIG}>
            <button
              type="button"
              onClick={() => onManageLoki(env)}
              className="group/btn flex flex-col items-center justify-center gap-1.5 rounded-xl border border-purple-500/20 bg-purple-500/5 p-2.5 text-center transition-all hover:border-purple-500/40 hover:bg-purple-500/15 cursor-pointer"
              title={t("actions.manageLogs")}
            >
              <IconGrafana className="size-4.5 group-hover/btn:scale-110 transition-transform" />
              <span className="text-[10px] font-bold text-purple-700 dark:text-purple-300 uppercase tracking-tight">
                {t("lokiLogs")}
              </span>
            </button>
          </CanInProject>

          <CanInProject I={ACTIONS.READ} a={RESOURCES.PROJECT_ALERT_RULE}>
            <button
              type="button"
              onClick={() => onManageAlerting(env)}
              className="group/btn flex flex-col items-center justify-center gap-1.5 rounded-xl border border-amber-500/20 bg-amber-500/5 p-2.5 text-center transition-all hover:border-amber-500/40 hover:bg-amber-500/15 cursor-pointer"
              title={t("actions.manageAlerting")}
            >
              <IconNotification className="size-4.5 group-hover/btn:scale-110 transition-transform" />
              <span className="text-[10px] font-bold text-amber-700 dark:text-amber-300 uppercase tracking-tight">
                {t("alerts")}
              </span>
            </button>
          </CanInProject>
        </div>
      </div>
    </m.div>
  );
}
