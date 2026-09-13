"use client";

import { useState, useEffect } from "react";
import { useTranslations } from "next-intl";
import { Play, RefreshCw, AlertTriangle, Radio, Pause } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/input";
import { Label } from "@/shared/ui/label";
import { Skeleton } from "@/shared/ui/skeleton";
import { useApiErrorMessage } from "@/shared/lib/handle-api-error";
import { formatDatetime, defaultRange } from "@/shared/lib/datetime";
import { useLokiConfigQuery, type LokiConfig } from "@/entities/loki-config";
import { useCloudflareConfigQuery } from "@/entities/cloudflare-config";
import { useLogQuery } from "../hooks/use-log-query";
import { useLogTail } from "../hooks/use-log-tail";
import { useCloudflareTrafficStatsQuery } from "../hooks/use-cloudflare-traffic-stats";
import type { LogEntry } from "../model/schema";

type TabKey = "loki" | "cloudflareTraffic";

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const exponent = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const value = bytes / 1024 ** exponent;
  return `${exponent === 0 ? value : value.toFixed(1)} ${units[exponent]}`;
}

function LogResultsTable({ entries }: { entries: LogEntry[] }) {
  const t = useTranslations("logViewer");
  if (entries.length === 0) {
    return <p className="text-sm text-muted-foreground">{t("query.empty")}</p>;
  }
  return (
    <div className="flex flex-col min-h-0 overflow-hidden rounded-2xl border border-border/50 bg-card/75 backdrop-blur-xl shadow-sm">
      <div className="flex-1 overflow-auto max-h-[60vh]">
        <table className="w-full min-w-[600px] text-left text-sm">
          <thead className="sticky top-0 z-10 border-b border-border/40 bg-card/95 backdrop-blur-md text-[11px] font-bold uppercase tracking-wider text-muted-foreground/90">
            <tr>
              <th scope="col" className="px-5 py-3 font-bold text-foreground/80">{t("query.timestamp")}</th>
              <th scope="col" className="px-5 py-3 font-bold text-foreground/80">{t("query.line")}</th>
              <th scope="col" className="px-5 py-3 font-bold text-foreground/80">{t("query.labels")}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border/40">
            {entries.map((entry, index) => (
              <tr key={`${entry.timestamp}-${index}`} className="transition-colors hover:bg-muted/30">
                <td className="whitespace-nowrap px-5 py-3 align-top font-mono text-xs text-muted-foreground">
                  {entry.timestamp}
                </td>
                <td className="px-5 py-3 align-top font-mono text-xs break-all">{entry.line}</td>
                <td className="px-5 py-3 align-top text-xs text-muted-foreground">
                  {Object.entries(entry.labels)
                    .map(([key, value]) => `${key}=${value}`)
                    .join(", ")}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
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

  const [queryParams, setQueryParams] = useState({
    query: defaultQuery,
    start: new Date(initialRange.start).toISOString(),
    end: new Date(initialRange.end).toISOString(),
    limit: 200,
  });

  const logQuery = useLogQuery(environmentId, queryParams);
  const tail = useLogTail(environmentId, query);

  const handleRun = (event: React.FormEvent) => {
    event.preventDefault();
    setQueryParams({
      query,
      start: new Date(start).toISOString(),
      end: new Date(end).toISOString(),
      limit: 200,
    });
  };

  const displayedEntries = tail.isLive ? tail.entries : logQuery.data;

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
          <Button type="submit" disabled={logQuery.isFetching || tail.isLive}>
            <Play className="mr-1.5 size-3.5" aria-hidden="true" />
            {logQuery.isFetching ? t("query.running") : t("query.run")}
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

      {(logQuery.isError || tail.error) && (
        <p role="alert" className="flex items-center gap-1.5 text-sm text-destructive">
          <AlertTriangle className="size-3.5" aria-hidden="true" /> {logQuery.error ? getErrorMessage(logQuery.error) : tail.error}
        </p>
      )}

      {!tail.isLive && (logQuery.isLoading || logQuery.isFetching) && <Skeleton className="h-32 w-full rounded-2xl" />}
      {displayedEntries && !logQuery.isLoading && <LogResultsTable entries={displayedEntries} />}
    </div>
  );
}

function CloudflareTrafficTab({ environmentId }: { environmentId: string }) {
  const t = useTranslations("logViewer");
  const getErrorMessage = useApiErrorMessage("logViewer");
  const initialRange = defaultRange(24 * 60); // last 24h
  const [since, setSince] = useState(initialRange.start);
  const [until, setUntil] = useState(initialRange.end);
  const { data, isLoading, error, refetch, isFetching } = useCloudflareTrafficStatsQuery(environmentId, {
    since: new Date(since).toISOString(),
    until: new Date(until).toISOString(),
  });

  if (isLoading) {
    return <Skeleton className="h-32 w-full" />;
  }

  if (data === null) {
    return <p className="text-sm text-muted-foreground">{t("traffic.notBound")}</p>;
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-3">
        <div className="space-y-1.5">
          <Label htmlFor="traffic-since">{t("traffic.since")}</Label>
          <Input
            id="traffic-since"
            type="datetime-local"
            value={since}
            onChange={(event) => setSince(event.target.value)}
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="traffic-until">{t("traffic.until")}</Label>
          <Input
            id="traffic-until"
            type="datetime-local"
            value={until}
            onChange={(event) => setUntil(event.target.value)}
          />
        </div>
        <Button type="button" variant="outline" onClick={() => refetch()} disabled={isFetching}>
          <RefreshCw className="mr-1.5 size-3.5" aria-hidden="true" />
          {t("traffic.refresh")}
        </Button>
      </div>

      {isFetching && <Skeleton className="h-32 w-full" />}

      {!isFetching && error && (
        <p className="flex items-center gap-2 text-sm text-destructive">
          <AlertTriangle className="size-3.5 shrink-0" aria-hidden="true" />
          {getErrorMessage(error)}
        </p>
      )}

      {!isFetching && !error && data && (
        <>
          <p className="text-xs text-muted-foreground">{t("traffic.hostnameHint", { hostname: data.hostname })}</p>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="rounded-2xl border border-border/50 bg-card/75 p-4">
              <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                {t("traffic.totalRequests")}
              </p>
              <p className="mt-1 text-2xl font-bold text-foreground">{data.totalRequests.toLocaleString()}</p>
            </div>
            <div className="rounded-2xl border border-border/50 bg-card/75 p-4">
              <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                {t("traffic.totalBytes")}
              </p>
              <p className="mt-1 text-2xl font-bold text-foreground">{formatBytes(data.totalBytes)}</p>
            </div>
          </div>

          {data.totalRequests === 0 ? (
            <p className="text-sm text-muted-foreground">{t("traffic.empty")}</p>
          ) : (
            <>
              {data.statusCodes.length > 0 && (
                <div className="flex flex-col gap-2 rounded-2xl border border-border/50 bg-card/75 p-4">
                  <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                    {t("traffic.statusCodes")}
                  </p>
                  {data.statusCodes.map((entry) => {
                    const widthPercent = Math.max(4, Math.round((entry.requests / data.totalRequests) * 100));
                    return (
                      <div key={entry.status} className="flex items-center gap-3 text-sm">
                        <span className="w-12 shrink-0 font-mono text-xs text-muted-foreground">{entry.status}</span>
                        <div className="h-2 flex-1 overflow-hidden rounded-full bg-muted">
                          <div className="h-full rounded-full bg-primary" style={{ width: `${widthPercent}%` }} />
                        </div>
                        <span className="w-16 shrink-0 text-right text-xs text-muted-foreground">
                          {entry.requests.toLocaleString()}
                        </span>
                      </div>
                    );
                  })}
                </div>
              )}

              {data.buckets.length > 0 && (
                <div className="flex flex-col min-h-0 overflow-hidden rounded-2xl border border-border/50 bg-card/75 backdrop-blur-xl shadow-sm">
                  <div className="flex-1 overflow-auto max-h-[60vh]">
                    <table className="w-full min-w-[500px] text-left text-sm">
                      <thead className="sticky top-0 z-10 border-b border-border/40 bg-card/95 backdrop-blur-md text-[11px] font-bold uppercase tracking-wider text-muted-foreground/90">
                        <tr>
                          <th scope="col" className="px-5 py-3 font-bold text-foreground/80">{t("traffic.bucketStart")}</th>
                          <th scope="col" className="px-5 py-3 font-bold text-foreground/80">{t("traffic.requests")}</th>
                          <th scope="col" className="px-5 py-3 font-bold text-foreground/80">{t("traffic.bytes")}</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-border/40">
                        {data.buckets.map((bucket) => (
                          <tr key={bucket.bucketStart} className="transition-colors hover:bg-muted/30">
                            <td className="whitespace-nowrap px-5 py-3 align-top font-mono text-xs text-muted-foreground">
                              {formatDatetime(bucket.bucketStart)}
                            </td>
                            <td className="px-5 py-3 align-top text-sm">{bucket.requests.toLocaleString()}</td>
                            <td className="px-5 py-3 align-top text-sm text-muted-foreground">
                              {formatBytes(bucket.bytes)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </>
          )}
        </>
      )}
    </div>
  );
}

function LogViewerTabSection({
  environmentId,
  tabs,
  activeTab,
  onSelectTab,
  lokiConfig,
  hasCloudflare,
}: {
  environmentId: string;
  tabs: { key: TabKey; label: string }[];
  activeTab: TabKey | null;
  onSelectTab: (key: TabKey) => void;
  lokiConfig: LokiConfig | null;
  hasCloudflare: boolean;
}) {
  const t = useTranslations("logViewer");
  return (
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
            onClick={() => onSelectTab(tab.key)}
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

      {lokiConfig && (
        <div role="tabpanel" id="log-viewer-panel-loki" aria-labelledby="log-viewer-tab-loki" hidden={activeTab !== "loki"}>
          {activeTab === "loki" && (
            <LokiQueryTab
              environmentId={environmentId}
              defaultQuery={lokiConfig.defaultQuery}
              defaultRangeMinutes={lokiConfig.defaultRangeMinutes}
            />
          )}
        </div>
      )}

      {hasCloudflare && (
        <div
          role="tabpanel"
          id="log-viewer-panel-cloudflareTraffic"
          aria-labelledby="log-viewer-tab-cloudflareTraffic"
          hidden={activeTab !== "cloudflareTraffic"}
        >
          {activeTab === "cloudflareTraffic" && <CloudflareTrafficTab environmentId={environmentId} />}
        </div>
      )}
    </section>
  );
}

/**
 * The reusable log-viewer surface — Loki config, Loki/Cloudflare-traffic
 * tabs — with no page-level chrome of its own. Shared by the full-page route
 * (`LogViewerPageContent`, which adds the `<h1>`/padding wrapper) and the
 * inline drawer opened from the environment chip on Project Detail. Only
 * shows a tab for whichever of Loki/Cloudflare is actually configured.
 */
export function LogViewerManager({ environmentId }: { environmentId: string }) {
  const t = useTranslations("logViewer");
  const { data: config, isLoading: lokiLoading } = useLokiConfigQuery(environmentId);
  const { data: cloudflareConfig, isLoading: cloudflareLoading } = useCloudflareConfigQuery(environmentId);


  const [activeTab, setActiveTab] = useState<TabKey | null>(null);

  const configLoading = lokiLoading || cloudflareLoading;
  const hasLoki = Boolean(config);
  const hasCloudflare = Boolean(cloudflareConfig);

  const tabs: { key: TabKey; label: string }[] = [
    ...(hasLoki ? [{ key: "loki" as const, label: t("tabs.loki") }] : []),
    ...(hasCloudflare ? [{ key: "cloudflareTraffic" as const, label: t("tabs.cloudflareTraffic") }] : []),
  ];
  const resolvedActiveTab = tabs.some((tab) => tab.key === activeTab) ? activeTab : (tabs[0]?.key ?? null);

  if (configLoading) {
    return <Skeleton className="h-28 w-full rounded-2xl" />;
  }

  return (
    <div className="flex flex-1 flex-col gap-6">
      {tabs.length > 0 ? (
        <LogViewerTabSection
          environmentId={environmentId}
          tabs={tabs}
          activeTab={resolvedActiveTab}
          onSelectTab={setActiveTab}
          lokiConfig={hasLoki ? (config ?? null) : null}
          hasCloudflare={hasCloudflare}
        />
      ) : (
        <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-border/60 bg-muted/20 py-14 text-center">
          <p className="text-sm font-medium text-muted-foreground">{t("config.noSourceConfigured")}</p>
        </div>
      )}
    </div>
  );
}
