"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { ScrollText } from "lucide-react";
import { Input } from "@/shared/ui/input";
import { Label } from "@/shared/ui/label";
import { formatDatetime } from "@/shared/lib/datetime";
import { useAuditLogsQuery } from "../hooks/use-audit-logs";
import { AUDIT_EVENT_TYPE, type AuditLogFilters } from "../api/fetchers";

import { m } from "@/shared/lib/motion";

import { Pagination } from "@/shared/ui/pagination";

export function AuditLogPageContent() {
  const t = useTranslations("auditLog");
  const [filters, setFilters] = useState<AuditLogFilters>({ limit: 15, offset: 0 });
  const { data } = useAuditLogsQuery(filters);

  const currentPage = Math.floor((filters.offset ?? 0) / (filters.limit ?? 15)) + 1;
  const pageSize = filters.limit ?? 15;

  return (
    <m.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="flex flex-1 min-h-0 flex-col gap-4"
    >
      <div className="shrink-0 flex flex-col gap-1">
        <div className="flex items-center gap-2.5">
          <h1 className="text-2xl font-extrabold tracking-tight text-foreground sm:text-3xl">
            {t("title")}
          </h1>
          <span className="inline-flex items-center rounded-full border border-purple-500/30 bg-purple-500/15 px-2.5 py-0.5 font-mono text-xs font-bold text-purple-600 dark:text-purple-400">
            {data.total}
          </span>
        </div>
        <p className="mt-1 text-sm text-muted-foreground">{t("description")}</p>
      </div>

      <div className="shrink-0 flex flex-wrap items-center gap-4 rounded-2xl border border-border/50 bg-card/60 p-4 backdrop-blur-md shadow-2xs">
        <div className="space-y-1.5 min-w-[240px]">
          <Label htmlFor="filter-project" className="text-xs font-semibold text-muted-foreground">{t("filters.projectId")}</Label>
          <Input
            id="filter-project"
            value={filters.projectId ?? ""}
            onChange={(e) =>
              setFilters((f) => ({ ...f, projectId: e.target.value || undefined, offset: 0 }))
            }
            className="h-9 rounded-xl border border-border/60 bg-background/80 px-3 text-xs shadow-2xs"
            placeholder={t("filters.projectPlaceholder")}
          />
        </div>
        <div className="space-y-1.5 min-w-[180px]">
          <Label htmlFor="filter-type" className="text-xs font-semibold text-muted-foreground">{t("filters.type")}</Label>
          <select
            id="filter-type"
            value={filters.type ?? ""}
            onChange={(e) =>
              setFilters((f) => ({
                ...f,
                type: (e.target.value || undefined) as AuditLogFilters["type"],
                offset: 0,
              }))
            }
            className="h-9 w-full rounded-xl border border-border/60 bg-background/80 px-3 text-xs font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary shadow-2xs"
          >
            <option value="">{t("filters.allTypes")}</option>
            {Object.values(AUDIT_EVENT_TYPE).map((type) => (
              <option key={type} value={type}>
                {type}
              </option>
            ))}
          </select>
        </div>
      </div>

      {data.items.length === 0 ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-3 rounded-3xl border border-border/50 bg-card/75 py-16 text-center backdrop-blur-xl shadow-lg">
          <div className="flex size-12 items-center justify-center rounded-2xl bg-muted/60 text-muted-foreground">
            <ScrollText className="size-6" aria-hidden />
          </div>
          <h2 className="text-lg font-bold text-foreground">{t("empty.title")}</h2>
        </div>
      ) : (
        <div className="flex flex-1 min-h-0 flex-col overflow-hidden rounded-3xl border border-border/50 bg-card/75 backdrop-blur-xl shadow-lg shadow-black/5 dark:shadow-black/20">
          <div className="flex-1 overflow-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 z-10 border-b border-border/40 bg-card/95 backdrop-blur-md text-left text-[11px] font-bold uppercase tracking-wider text-muted-foreground/90">
                <tr>
                  <th className="px-6 py-4 font-bold text-foreground/80">{t("table.timestamp")}</th>
                  <th className="px-6 py-4 font-bold text-foreground/80">{t("table.action")}</th>
                  <th className="px-6 py-4 font-bold text-foreground/80">{t("table.actor")}</th>
                  <th className="px-6 py-4 font-bold text-foreground/80">{t("table.message")}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/40">
                {data.items.map((entry) => (
                  <tr key={entry.id} className="transition-colors hover:bg-muted/40">
                    <td className="px-6 py-4 font-mono text-xs text-muted-foreground whitespace-nowrap">
                      {formatDatetime(entry.timestamp)}
                    </td>
                    <td className="px-6 py-4">
                      <span className="inline-flex rounded-lg border border-purple-500/30 bg-purple-500/10 px-2 py-0.5 font-mono text-[11px] font-semibold text-purple-600 dark:text-purple-400">
                        {entry.action}
                      </span>
                    </td>
                    <td className="px-6 py-4 font-mono text-xs text-muted-foreground">
                      {entry.actor.email ?? "—"}
                    </td>
                    <td className="px-6 py-4 text-foreground font-medium">
                      {entry.message}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="shrink-0">
            <Pagination
              page={currentPage}
              pageSize={pageSize}
              total={data.total}
              pageSizeOptions={[10, 15, 25, 50]}
              onPageChange={(newPage) =>
                setFilters((f) => ({ ...f, offset: (newPage - 1) * (f.limit ?? 15) }))
              }
              onPageSizeChange={(newLimit) =>
                setFilters((f) => ({ ...f, limit: newLimit, offset: 0 }))
              }
            />
          </div>
        </div>
      )}
    </m.div>
  );
}
