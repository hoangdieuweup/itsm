import { AlertCircle, Eye, CheckCircle2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { INCIDENT_STATUS, type IncidentStatus } from "@/entities/incident";

const STATUS_STYLES: Record<IncidentStatus, { icon: typeof AlertCircle; className: string }> = {
  [INCIDENT_STATUS.OPEN]: {
    icon: AlertCircle,
    className: "bg-red-50 text-red-700 dark:bg-red-950/60 dark:text-red-300",
  },
  [INCIDENT_STATUS.ACKNOWLEDGED]: {
    icon: Eye,
    className: "bg-amber-50 text-amber-700 dark:bg-amber-950/60 dark:text-amber-300",
  },
  [INCIDENT_STATUS.RESOLVED]: {
    icon: CheckCircle2,
    className: "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300",
  },
};

export function IncidentStatusBadge({ status }: { status: IncidentStatus }) {
  const t = useTranslations("incidents");
  const { icon: Icon, className } = STATUS_STYLES[status];
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase ${className}`}
    >
      <Icon className="size-3" aria-hidden="true" />
      {t(`status.${status}`)}
    </span>
  );
}
