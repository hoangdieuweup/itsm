"use client";

import { useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { Waypoints, Plus, Trash2, RefreshCw, KeyRound } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { ConfirmDialog } from "@/shared/ui/confirm-dialog";
import { Can } from "@/entities/permission";
import { ACTIONS, PERMISSIONS } from "@/shared/constants/permissions";
import {
  useTunnelsQuery,
  useDeleteTunnel,
  useRefreshTunnelStatus,
  useRevealTunnelToken,
  useSyncTunnels,
} from "../hooks/use-tunnels";
import { useTunnelHostnamesQuery } from "../hooks/use-tunnel-hostnames";
import type { CloudflareTunnel } from "../model/schema";
import { TunnelStatusBadge } from "./tunnel-status-badge";
import { CreateTunnelDialog } from "./create-tunnel-dialog";
import { TunnelHostnamesPanel } from "./tunnel-hostnames-panel";

/**
 * Always-visible preview of the hostname(s) this tunnel routes for the
 * current environment — shown directly on the collapsed row so the mapping
 * is visible without clicking into the row first. Reuses the same query the
 * expanded `TunnelHostnamesPanel` uses; React Query dedupes/caches it.
 */
function TunnelHostnamePreview({ environmentId, tunnelId }: { environmentId: string; tunnelId: string }) {
  const t = useTranslations("cloudflareTunnels");
  const { data: hostnames = [], isLoading } = useTunnelHostnamesQuery(environmentId, tunnelId, true);

  if (isLoading) {
    return null;
  }
  if (hostnames.length === 0) {
    return <span className="text-xs italic text-muted-foreground">{t("hostnames.noneMatched")}</span>;
  }
  return (
    <span className="flex flex-wrap gap-x-3 gap-y-0.5">
      {hostnames.map((hostname) => (
        <span key={hostname.id} className="font-mono text-xs text-muted-foreground">
          {t("hostnames.mapping", { hostname: hostname.hostname, service: hostname.service })}
        </span>
      ))}
    </span>
  );
}

/**
 * The reusable tunnel-management surface — list, status, hostnames — with no
 * page-level chrome of its own. Shared by the full-page route
 * (`CloudflareTunnelsPageContent`, which adds the `<h1>`/padding wrapper) and
 * the inline drawer opened from the environment chip on Project Detail.
 */
export function TunnelsManager({ environmentId }: { environmentId: string }) {
  const t = useTranslations("cloudflareTunnels");
  const { data: tunnels = [] } = useTunnelsQuery(environmentId);
  const deleteTunnel = useDeleteTunnel(environmentId);
  const refreshStatus = useRefreshTunnelStatus(environmentId);
  const revealToken = useRevealTunnelToken(environmentId);
  const syncMutation = useSyncTunnels(environmentId);

  const syncTriggered = useRef(false);
  useEffect(() => {
    if (!syncTriggered.current) {
      syncTriggered.current = true;
      syncMutation.mutate();
    }
  }, [syncMutation]);

  const [createOpen, setCreateOpen] = useState(false);
  const [selectedTunnelId, setSelectedTunnelId] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<CloudflareTunnel | null>(null);
  const [revealedToken, setRevealedToken] = useState<{ tunnelId: string; token: string } | null>(null);

  return (
    <div className="flex flex-1 flex-col gap-6">
      <section className="flex flex-col gap-3 rounded-xl border bg-card p-5">
        <div className="flex items-center justify-between">
          <h2 className="flex items-center gap-2 text-sm font-bold text-foreground">
            <Waypoints className="size-4" aria-hidden="true" /> {t("title")}
          </h2>
          <Can I={ACTIONS.MANAGE} a={PERMISSIONS.CLOUDFLARE_ACCOUNT.RESOURCE}>
            <Button size="sm" onClick={() => setCreateOpen(true)}>
              <Plus className="mr-1.5 size-3.5" aria-hidden="true" /> {t("addTunnel")}
            </Button>
          </Can>
        </div>

        {tunnels.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("empty")}</p>
        ) : (
          <div className="flex flex-col divide-y">
            {tunnels.map((tunnel) => (
              <div
                key={tunnel.id}
                className={`flex items-center justify-between py-3 ${
                  selectedTunnelId === tunnel.id ? "bg-muted/40" : ""
                }`}
              >
                <button
                  type="button"
                  onClick={() => setSelectedTunnelId(tunnel.id)}
                  className="flex flex-1 flex-col items-start gap-1 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                >
                  <span className="flex items-center gap-3">
                    <span className="font-medium text-foreground">{tunnel.name}</span>
                    <TunnelStatusBadge status={tunnel.status} />
                  </span>
                  <TunnelHostnamePreview environmentId={environmentId} tunnelId={tunnel.id} />
                </button>
                <Can I={ACTIONS.MANAGE} a={PERMISSIONS.CLOUDFLARE_ACCOUNT.RESOURCE}>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => refreshStatus.mutate(tunnel.id)}
                      aria-label={t("refreshStatus")}
                      className="cursor-pointer text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                    >
                      <RefreshCw className="size-3.5" aria-hidden="true" />
                    </button>
                    <button
                      type="button"
                      onClick={async () => {
                        const token = await revealToken.mutateAsync(tunnel.id);
                        setRevealedToken({ tunnelId: tunnel.id, token });
                      }}
                      aria-label={t("revealToken")}
                      className="cursor-pointer text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                    >
                      <KeyRound className="size-3.5" aria-hidden="true" />
                    </button>
                    <button
                      type="button"
                      onClick={() => setDeleteTarget(tunnel)}
                      aria-label={t("deleteConfirm.action")}
                      className="cursor-pointer text-muted-foreground hover:text-destructive focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                    >
                      <Trash2 className="size-3.5" aria-hidden="true" />
                    </button>
                  </div>
                </Can>
              </div>
            ))}
          </div>
        )}
      </section>

      {revealedToken && (
        <section className="flex flex-col gap-2 rounded-xl border border-amber-300 bg-amber-50 p-4 dark:border-amber-800 dark:bg-amber-950/40">
          <p className="text-xs font-semibold uppercase text-amber-700 dark:text-amber-300">
            {t("tokenRevealed.title")}
          </p>
          <code className="break-all rounded bg-background px-2 py-1.5 font-mono text-xs">
            {revealedToken.token}
          </code>
          <p className="text-xs text-muted-foreground">{t("tokenRevealed.hint")}</p>
        </section>
      )}

      {selectedTunnelId && <TunnelHostnamesPanel environmentId={environmentId} tunnelId={selectedTunnelId} />}

      {createOpen && <CreateTunnelDialog environmentId={environmentId} onClose={() => setCreateOpen(false)} />}

      <ConfirmDialog
        isOpen={deleteTarget !== null}
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => {
          if (deleteTarget) {
            deleteTunnel.mutate(deleteTarget.id, {
              onSuccess: () => {
                setDeleteTarget(null);
                if (selectedTunnelId === deleteTarget.id) setSelectedTunnelId(null);
              },
            });
          }
        }}
        title={t("deleteConfirm.title")}
        description={t("deleteConfirm.description", { name: deleteTarget?.name ?? "" })}
        variant="destructive"
        isLoading={deleteTunnel.isPending}
      />
    </div>
  );
}
