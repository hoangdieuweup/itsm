"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { ScrollText, Pencil, Trash2, Play, RefreshCw, AlertTriangle, Radio, Pause } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/input";
import { Label } from "@/shared/ui/label";
import { Skeleton } from "@/shared/ui/skeleton";
import { ConfirmDialog } from "@/shared/ui/confirm-dialog";
import { Can } from "@/entities/permission";
import { ACTIONS, RESOURCES } from "@/shared/constants/permissions";
import { useApiErrorMessage } from "@/shared/lib/handle-api-error";
import { useLokiConfigQuery, useDeleteLokiConfig } from "../hooks/use-loki-config";
import { useRunLogQuery } from "../hooks/use-log-query";
import { useLogTail } from "../hooks/use-log-tail";
import { useCloudflareAuditLogsQuery } from "../hooks/use-cloudflare-audit-logs";
import type { LogEntry } from "../model/schema";
import { LokiConfigFormDialog } from "./loki-config-form-dialog";

type TabKey = "loki" | "cloudflareAuditLog";

function toDatetimeLocal(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

function defaultRange(rangeMinutes: number): { start: string; end: string } {
  const end = new Date();
  const start = new Date(end.getTime() - rangeMinutes * 60_000);
  return { start: toDatetimeLocal(start), end: toDatetimeLocal(end) };
}

function LogResultsTable({ entries }: { entries: LogEntry[] }) {
  const t = useTranslations("logViewer");
  if (entries.length === 0) {
    return <p className="text-sm text-muted-foreground">{t("query.empty")}</p>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b text-left text-xs uppercase text-muted-foreground">
            <th className="py-2 pr-4">{t("query.timestamp")}</th>
            <th className="py-2 pr-4">{t("query.line")}</th>
            <th className="py-2">{t("query.labels")}</th>
          </tr>
        </thead>
        <tbody className="divide-y">
          {entries.map((entry, index) => (
            <tr key={`${entry.timestamp}-${index}`}>
              <td className="whitespace-nowrap py-2 pr-4 align-top font-mono text-xs text-muted-foreground">
                {entry.timestamp}
              </td>
              <td className="py-2 pr-4 align-top font-mono text-xs break-all">{entry.line}</td>
              <td className="py-2 align-top text-xs text-muted-foreground">
                {Object.entries(entry.labels)
                  .map(([key, value]) => `${key}=${value}`)
                  .join(", ")}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TimeRangeInputs({
  start,
  end,
  onStartChange,
  onEndChange,
  disabled,
}: {
  start: string;
  end: string;
  onStartChange: (value: string) => void;
  onEndChange: (value: string) => void;
  disabled: boolean;
}) {
  const t = useTranslations("logViewer");
  const describedBy = disabled ? "loki-live-hint" : undefined;
  return (
    <>
      <div className="space-y-1.5">
        <Label htmlFor="loki-query-start">{t("query.start")}</Label>
        <Input
          id="loki-query-start"
          type="datetime-local"
          value={start}
          onChange={(event) => onStartChange(event.target.value)}
          disabled={disabled}
          aria-describedby={describedBy}
          required
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="loki-query-end">{t("query.end")}</Label>
        <Input
          id="loki-query-end"
          type="datetime-local"
          value={end}
          onChange={(event) => onEndChange(event.target.value)}
          disabled={disabled}
          aria-describedby={describedBy}
          required
        />
      </div>
    </>
  );
}

function LiveToggleButton({ isLive, onStart, onStop }: { isLive: boolean; onStart: () => void; onStop: () => void }) {
  const t = useTranslations("logViewer");
  const Icon = isLive ? Pause : Radio;
  return (
    <Button
      type="button"
      variant={isLive ? "destructive" : "outline"}
      aria-pressed={isLive}
      onClick={isLive ? onStop : onStart}
    >
      <Icon className="mr-1.5 size-3.5" aria-hidden="true" />
      {isLive ? t("query.pause") : t("query.live")}
    </Button>
  );
}

function LokiQueryTab({ environmentId, defaultQuery, defaultRangeMinutes }: {
  environmentId: string;
  defaultQuery: string;
  defaultRangeMinutes: number;
}) {
  const t = useTranslations("logViewer");
  const getErrorMessage = useApiErrorMessage("logViewer");
  const initialRange = defaultRange(defaultRangeMinutes);
  const [query, setQuery] = useState(defaultQuery);
  const [start, setStart] = useState(initialRange.start);
  const [end, setEnd] = useState(initialRange.end);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const runQuery = useRunLogQuery(environmentId);
  const tail = useLogTail(environmentId, query);

  const handleRun = (event: React.FormEvent) => {
    event.preventDefault();
    setErrorMessage(null);
    runQuery.mutate(
      { query, start: new Date(start).toISOString(), end: new Date(end).toISOString(), limit: 200 },
      { onError: (err) => setErrorMessage(getErrorMessage(err)) },
    );
  };

  const displayedEntries = tail.isLive ? tail.entries : runQuery.data;

  return (
    <div className="flex flex-col gap-4">
      <form onSubmit={handleRun} className="flex flex-col gap-3">
        <div className="space-y-1.5">
          <Label htmlFor="loki-query">{t("query.queryLabel")}</Label>
          <Input
            id="loki-query"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            className="font-mono"
            required
          />
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <TimeRangeInputs
            start={start}
            end={end}
            onStartChange={setStart}
            onEndChange={setEnd}
            disabled={tail.isLive}
          />
          <Button type="submit" disabled={runQuery.isPending || tail.isLive}>
            <Play className="mr-1.5 size-3.5" aria-hidden="true" />
            {runQuery.isPending ? t("query.running") : t("query.run")}
          </Button>
          <LiveToggleButton isLive={tail.isLive} onStart={tail.start} onStop={tail.stop} />
        </div>
        {tail.isLive && (
          <p id="loki-live-hint" className="sr-only">
            {t("query.liveHint")}
          </p>
        )}
      </form>

      {tail.isLive && (
        <p role="status" aria-atomic="true" className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <Radio className="size-3 animate-pulse text-primary" aria-hidden="true" /> {t("query.live")}
        </p>
      )}

      {(errorMessage ?? tail.error) && (
        <p role="alert" className="flex items-center gap-1.5 text-sm text-destructive">
          <AlertTriangle className="size-3.5" aria-hidden="true" /> {errorMessage ?? tail.error}
        </p>
      )}

      {!tail.isLive && runQuery.isPending && <Skeleton className="h-32 w-full" />}
      {displayedEntries && <LogResultsTable entries={displayedEntries} />}
    </div>
  );
}

function CloudflareAuditLogTab({ environmentId }: { environmentId: string }) {
  const t = useTranslations("logViewer");
  const [since, setSince] = useState("");
  const [before, setBefore] = useState("");
  const { data, isLoading, refetch, isFetching } = useCloudflareAuditLogsQuery(environmentId, {
    since: since ? new Date(since).toISOString() : undefined,
    before: before ? new Date(before).toISOString() : undefined,
  });

  if (isLoading) {
    return <Skeleton className="h-32 w-full" />;
  }

  if (data === null) {
    return <p className="text-sm text-muted-foreground">{t("auditLog.notBound")}</p>;
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-3">
        <div className="space-y-1.5">
          <Label htmlFor="audit-log-since">{t("auditLog.since")}</Label>
          <Input
            id="audit-log-since"
            type="datetime-local"
            value={since}
            onChange={(event) => setSince(event.target.value)}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="audit-log-before">{t("auditLog.before")}</Label>
          <Input
            id="audit-log-before"
            type="datetime-local"
            value={before}
            onChange={(event) => setBefore(event.target.value)}
          />
        </div>
        <Button type="button" variant="outline" onClick={() => refetch()} disabled={isFetching}>
          <RefreshCw className="mr-1.5 size-3.5" aria-hidden="true" />
          {t("auditLog.refresh")}
        </Button>
      </div>

      {isFetching && <Skeleton className="h-32 w-full" />}

      {!isFetching && data && data.length === 0 && (
        <p className="text-sm text-muted-foreground">{t("auditLog.empty")}</p>
      )}

      {!isFetching && data && data.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left text-xs uppercase text-muted-foreground">
                <th className="py-2 pr-4">{t("auditLog.when")}</th>
                <th className="py-2 pr-4">{t("auditLog.actor")}</th>
                <th className="py-2 pr-4">{t("auditLog.action")}</th>
                <th className="py-2 pr-4">{t("auditLog.resource")}</th>
                <th className="py-2">{t("auditLog.newValue")}</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {data.map((entry) => (
                <tr key={entry.id}>
                  <td className="whitespace-nowrap py-2 pr-4 align-top font-mono text-xs text-muted-foreground">
                    {entry.when}
                  </td>
                  <td className="py-2 pr-4 align-top">{entry.actorEmail ?? "—"}</td>
                  <td className="py-2 pr-4 align-top font-mono text-xs">{entry.actionType}</td>
                  <td className="py-2 pr-4 align-top text-muted-foreground">
                    {entry.resourceType ?? "—"}
                    {entry.resourceProduct ? ` (${entry.resourceProduct})` : ""}
                  </td>
                  <td className="py-2 align-top break-all text-muted-foreground">{entry.newValue ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

/**
 * The reusable log-viewer surface — Loki config, Loki/Cloudflare-audit-log
 * tabs — with no page-level chrome of its own. Shared by the full-page route
 * (`LogViewerPageContent`, which adds the `<h1>`/padding wrapper) and the
 * inline drawer opened from the environment chip on Project Detail.
 */
export function LogViewerManager({ environmentId }: { environmentId: string }) {
  const t = useTranslations("logViewer");
  const { data: config, isLoading: configLoading } = useLokiConfigQuery(environmentId);
  const deleteConfig = useDeleteLokiConfig(environmentId);

  const [formOpen, setFormOpen] = useState(false);
  const [deleteConfirmOpen, setDeleteConfirmOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<TabKey>("loki");

  const tabs: { key: TabKey; label: string }[] = [
    { key: "loki", label: t("tabs.loki") },
    { key: "cloudflareAuditLog", label: t("tabs.cloudflareAuditLog") },
  ];

  return (
    <div className="flex flex-1 flex-col gap-6">
      {configLoading && <Skeleton className="h-24 w-full" />}

      {!configLoading && !config && (
        <section className="flex flex-col gap-3 rounded-xl border bg-card p-5">
          <h2 className="flex items-center gap-2 text-sm font-bold text-foreground">
            <ScrollText className="size-4 text-primary" aria-hidden="true" /> {t("config.title")}
          </h2>
          <p className="text-sm text-muted-foreground">{t("config.description")}</p>
          <Can I={ACTIONS.UPDATE} a={RESOURCES.ENVIRONMENT}>
            <div>
              <Button size="sm" onClick={() => setFormOpen(true)}>
                {t("config.configure")}
              </Button>
            </div>
          </Can>
        </section>
      )}

      {!configLoading && config && (
        <>
          <section className="flex flex-col gap-3 rounded-xl border bg-card p-5">
            <div className="flex items-center justify-between">
              <h2 className="flex items-center gap-2 text-sm font-bold text-foreground">
                <ScrollText className="size-4 text-primary" aria-hidden="true" /> {config.endpointUrl}
              </h2>
              <Can I={ACTIONS.UPDATE} a={RESOURCES.ENVIRONMENT}>
                <div className="flex gap-2">
                  <button
                    type="button"
                    onClick={() => setFormOpen(true)}
                    aria-label={t("config.edit")}
                    className="cursor-pointer text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                  >
                    <Pencil className="size-3.5" aria-hidden="true" />
                  </button>
                  <button
                    type="button"
                    onClick={() => setDeleteConfirmOpen(true)}
                    aria-label={t("config.delete")}
                    className="cursor-pointer text-muted-foreground hover:text-destructive focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                  >
                    <Trash2 className="size-3.5" aria-hidden="true" />
                  </button>
                </div>
              </Can>
            </div>
          </section>

          <section className="flex flex-col gap-4 rounded-xl border bg-card p-5">
            <div role="tablist" aria-label={t("config.title")} className="flex gap-1 border-b">
              {tabs.map((tab) => (
                <button
                  key={tab.key}
                  type="button"
                  role="tab"
                  id={`log-viewer-tab-${tab.key}`}
                  aria-selected={activeTab === tab.key}
                  aria-controls={`log-viewer-panel-${tab.key}`}
                  onClick={() => setActiveTab(tab.key)}
                  className={`cursor-pointer border-b-2 px-3 py-2 text-sm font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary ${
                    activeTab === tab.key
                      ? "border-primary text-foreground"
                      : "border-transparent text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>

            <div
              role="tabpanel"
              id="log-viewer-panel-loki"
              aria-labelledby="log-viewer-tab-loki"
              hidden={activeTab !== "loki"}
            >
              {activeTab === "loki" && (
                <LokiQueryTab
                  environmentId={environmentId}
                  defaultQuery={config.defaultQuery}
                  defaultRangeMinutes={config.defaultRangeMinutes}
                />
              )}
            </div>

            <div
              role="tabpanel"
              id="log-viewer-panel-cloudflareAuditLog"
              aria-labelledby="log-viewer-tab-cloudflareAuditLog"
              hidden={activeTab !== "cloudflareAuditLog"}
            >
              {activeTab === "cloudflareAuditLog" && <CloudflareAuditLogTab environmentId={environmentId} />}
            </div>
          </section>
        </>
      )}

      {formOpen && (
        <LokiConfigFormDialog environmentId={environmentId} config={config ?? null} onClose={() => setFormOpen(false)} />
      )}

      <ConfirmDialog
        isOpen={deleteConfirmOpen}
        onClose={() => setDeleteConfirmOpen(false)}
        onConfirm={() => {
          deleteConfig.mutate(undefined, { onSuccess: () => setDeleteConfirmOpen(false) });
        }}
        title={t("config.deleteConfirm.title")}
        description={t("config.deleteConfirm.description")}
        variant="destructive"
        isLoading={deleteConfig.isPending}
      />
    </div>
  );
}
