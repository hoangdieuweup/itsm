import { CheckCircle2, AlertTriangle, XCircle, HelpCircle } from "lucide-react";
import { useTranslations } from "next-intl";
import type { TunnelStatus } from "../model/schema";

const STATUS_STYLES: Record<TunnelStatus, { icon: typeof CheckCircle2; className: string }> = {
  healthy: {
    icon: CheckCircle2,
    className: "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300",
  },
  degraded: {
    icon: AlertTriangle,
    className: "bg-amber-50 text-amber-700 dark:bg-amber-950/60 dark:text-amber-300",
  },
  down: {
    icon: XCircle,
    className: "bg-red-50 text-red-700 dark:bg-red-950/60 dark:text-red-300",
  },
  unknown: {
    icon: HelpCircle,
    className: "bg-muted text-muted-foreground",
  },
};

export function TunnelStatusBadge({ status }: { status: TunnelStatus }) {
  const t = useTranslations("cloudflareTunnels");
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
