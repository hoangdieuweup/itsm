"use client";

import { useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { Trash2, RefreshCw, KeyRound, ArrowRight } from "lucide-react";
import { ConfirmDialog } from "@/shared/ui/confirm-dialog";
import { CanInProject } from "@/entities/permission";
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
import { TunnelHostnamesPanel } from "./tunnel-hostnames-panel";
import { IconCloudflare } from "@/shared/ui/icons";

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
    <div className="flex flex-col gap-1.5 mt-2 w-full">
      {hostnames.map((hostname) => (
        <div
          key={hostname.id}
          className="inline-flex items-center gap-2 rounded-xl bg-muted/50 border border-border/40 px-2.5 py-1 font-mono text-xs text-muted-foreground flex-wrap max-w-full"
        >
          <span className="font-semibold text-foreground">
            {hostname.hostname}
          </span>
          <ArrowRight className="size-3 text-muted-foreground/60 shrink-0" />
          <span className="text-primary font-medium">{hostname.service}</span>
        </div>
      ))}
    </div>
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
  const { data: tunnels = [], isLoading: tunnelsLoading } = useTunnelsQuery(environmentId);
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

  const [selectedTunnelId, setSelectedTunnelId] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<CloudflareTunnel | null>(null);
  const [revealedToken, setRevealedToken] = useState<{ tunnelId: string; token: string } | null>(null);

  const activeTunnelId = selectedTunnelId ?? (tunnels.length > 0 ? tunnels[0].id : null);

  return (
    <div className="flex flex-1 flex-col gap-6">
      <section className="flex flex-col gap-4 rounded-3xl border border-border/60 bg-gradient-to-br from-card via-card/90 to-blue-500/5 p-6 backdrop-blur-xl shadow-lg shadow-black/5 dark:shadow-black/20">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <IconCloudflare className="size-8 shrink-0 rounded-xl shadow-xs" />
            <div>
              <h2 className="text-base font-bold tracking-tight text-foreground">
                {t("title")}
              </h2>
              <p className="text-xs text-muted-foreground">
                {t("subtitle")}
              </p>
            </div>
          </div>
        </div>

        {tunnelsLoading ? (
          <div className="flex flex-col gap-3">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 rounded-2xl border border-border/60 bg-card/60 p-4.5 animate-pulse">
              <div className="flex flex-col gap-2.5 w-full max-w-sm">
                <div className="h-5 w-32 rounded-md bg-muted/80" />
                <div className="h-4 w-56 rounded-md bg-muted/50" />
              </div>
              <div className="flex gap-2">
                <div className="size-8 rounded-xl bg-muted/60" />
                <div className="size-8 rounded-xl bg-muted/60" />
              </div>
            </div>
          </div>
        ) : tunnels.length === 0 ? (
          <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-border/60 bg-muted/20 py-10 px-4 text-center">
            <IconCloudflare className="size-12 rounded-2xl shadow-xs mb-3 opacity-90" />
            <p className="text-sm font-bold text-foreground">{t("empty")}</p>
          </div>
        ) : (
          <div className="flex flex-col gap-3">
            {tunnels.map((tunnel) => (
              <div
                key={tunnel.id}
                className={`flex flex-col sm:flex-row sm:items-center justify-between gap-4 rounded-2xl border border-border/60 bg-card/75 p-4.5 backdrop-blur-md transition-all hover:border-blue-500/40 hover:shadow-xs ${
                  activeTunnelId === tunnel.id
                    ? "border-blue-500/50 bg-card/90 shadow-xs ring-1 ring-blue-500/20"
                    : "hover:bg-card"
                }`}
              >
                <button
                  type="button"
                  onClick={() => setSelectedTunnelId(tunnel.id)}
                  className="flex flex-1 flex-col items-start gap-1 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary cursor-pointer"
                >
                  <div className="flex items-center gap-3 flex-wrap">
                    <span className="font-bold text-foreground text-sm">{tunnel.name}</span>
                    <TunnelStatusBadge status={tunnel.status} />
                  </div>
                  <TunnelHostnamePreview environmentId={environmentId} tunnelId={tunnel.id} />
                </button>
                <div className="flex items-center gap-1 shrink-0 self-end sm:self-auto">
                  <CanInProject I={ACTIONS.REFRESH_STATUS} a={PERMISSIONS.PROJECT_CLOUDFLARE_TUNNEL.RESOURCE}>
                    <button
                      type="button"
                      onClick={() => refreshStatus.mutate(tunnel.id)}
                      aria-label={t("refreshStatus")}
                      className="p-2 rounded-xl text-muted-foreground hover:text-foreground hover:bg-muted/80 transition-colors cursor-pointer"
                      title={t("refreshStatus")}
                    >
                      <RefreshCw className="size-4" aria-hidden="true" />
                    </button>
                  </CanInProject>
                  {/* reveal-token/delete are ACCOUNT-level-only actions (no
                      project-scoped twin exists — see the ownership fix's
                      D8) — CanInProject on the old resource name correctly
                      shows these only when the global half of the union
                      grants them. */}
                  <CanInProject I={ACTIONS.REVEAL_TOKEN} a={PERMISSIONS.CLOUDFLARE_TUNNEL.RESOURCE}>
                    <button
                      type="button"
                      onClick={async () => {
                        const token = await revealToken.mutateAsync(tunnel.id);
                        setRevealedToken({ tunnelId: tunnel.id, token });
                      }}
                      aria-label={t("revealToken")}
                      className="p-2 rounded-xl text-muted-foreground hover:text-foreground hover:bg-muted/80 transition-colors cursor-pointer"
                      title={t("revealToken")}
                    >
                      <KeyRound className="size-4" aria-hidden="true" />
                    </button>
                  </CanInProject>
                  <CanInProject I={ACTIONS.DELETE} a={PERMISSIONS.CLOUDFLARE_TUNNEL.RESOURCE}>
                    <button
                      type="button"
                      onClick={() => setDeleteTarget(tunnel)}
                      aria-label={t("deleteConfirm.action")}
                      className="p-2 rounded-xl text-muted-foreground hover:text-destructive hover:bg-rose-500/10 transition-colors cursor-pointer"
                      title={t("deleteConfirm.action")}
                    >
                      <Trash2 className="size-4" aria-hidden="true" />
                    </button>
                  </CanInProject>
                </div>
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

      {activeTunnelId && <TunnelHostnamesPanel environmentId={environmentId} tunnelId={activeTunnelId} />}

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
