"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { ScrollText } from "lucide-react";
import { Input } from "@/shared/ui/input";
import { Label } from "@/shared/ui/label";
import { useAuditLogsQuery } from "../hooks/use-audit-logs";
import { AUDIT_EVENT_TYPE, type AuditLogFilters } from "../api/fetchers";

export function AuditLogPageContent() {
  const t = useTranslations("auditLog");
  const [filters, setFilters] = useState<AuditLogFilters>({ limit: 50, offset: 0 });
  const { data } = useAuditLogsQuery(filters);

  return (
    <div className="flex flex-1 flex-col gap-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-xl font-bold text-foreground">{t("title")}</h1>
        <p className="text-sm text-muted-foreground">{t("description")}</p>
      </div>

      <div className="flex flex-wrap gap-4 rounded-xl border bg-card p-4">
        <div className="space-y-1.5">
          <Label htmlFor="filter-project">{t("filters.projectId")}</Label>
          <Input
            id="filter-project"
            value={filters.projectId ?? ""}
            onChange={(e) =>
              setFilters((f) => ({ ...f, projectId: e.target.value || undefined, offset: 0 }))
            }
            className="h-9 w-64"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="filter-type">{t("filters.type")}</Label>
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
            className="h-9 rounded-md border bg-background px-3 text-sm"
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
        <div className="flex flex-1 flex-col items-center justify-center gap-3 rounded-xl border bg-card py-16 text-center">
          <div className="flex size-12 items-center justify-center rounded-xl bg-muted text-muted-foreground">
            <ScrollText className="size-6" aria-hidden />
          </div>
          <h2 className="text-lg font-semibold text-foreground">{t("empty.title")}</h2>
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border bg-card">
          <table className="w-full text-sm">
            <thead className="border-b bg-muted/40 text-left text-xs font-semibold uppercase tracking-wider text-muted-foreground">
              <tr>
                <th className="px-4 py-3">{t("table.timestamp")}</th>
                <th className="px-4 py-3">{t("table.action")}</th>
                <th className="px-4 py-3">{t("table.actor")}</th>
                <th className="px-4 py-3">{t("table.message")}</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {data.items.map((entry) => (
                <tr key={entry.id} className="hover:bg-muted/30">
                  <td className="px-4 py-3 whitespace-nowrap text-muted-foreground">
                    {new Date(entry.timestamp).toLocaleString()}
                  </td>
                  <td className="px-4 py-3 font-mono text-xs font-medium text-foreground">
                    {entry.action}
                  </td>
                  <td className="px-4 py-3 text-muted-foreground">{entry.actor.email ?? "—"}</td>
                  <td className="px-4 py-3 text-foreground">{entry.message}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
