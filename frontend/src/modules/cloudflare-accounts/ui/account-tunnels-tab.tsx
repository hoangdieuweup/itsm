"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { Cable, Plus, Trash2, Wifi, WifiOff, AlertTriangle, Server, Copy, Check, Key } from "lucide-react";
import { fetchAccountTunnels, cloudflareAccountsKeys, type CfTunnel } from "@/entities/cloudflare-account";
import { Button } from "@/shared/ui/button";
import { Skeleton } from "@/shared/ui/skeleton";
import { ConfirmDialog } from "@/shared/ui/confirm-dialog";
import { useCreateAccountTunnel, useDeleteAccountTunnel } from "../hooks/use-account-mutations";

/* ── Status badge ── */
function TunnelStatusBadge({ status }: { status: CfTunnel["status"] }) {
  const config: Record<CfTunnel["status"], { color: string; icon: React.ReactNode; label: string }> = {
    healthy: {
      color: "border-emerald-500/30 bg-emerald-500/15 text-emerald-600 dark:text-emerald-400",
      icon: <Wifi className="size-3" />,
      label: "Healthy",
    },
    degraded: {
      color: "border-amber-500/30 bg-amber-500/15 text-amber-600 dark:text-amber-400",
      icon: <AlertTriangle className="size-3" />,
      label: "Degraded",
    },
    down: {
      color: "border-rose-500/30 bg-rose-500/15 text-rose-600 dark:text-rose-400",
      icon: <WifiOff className="size-3" />,
      label: "Down",
    },
    inactive: {
      color: "border-border/70 bg-muted/60 text-muted-foreground",
      icon: <Server className="size-3" />,
      label: "Inactive",
    },
  };
  const c = config[status] ?? config.inactive;
  return (
    <span className={`inline-flex items-center gap-1 rounded-lg border px-2 py-0.5 text-[11px] font-bold uppercase tracking-wider ${c.color}`}>
      {c.icon}
      {c.label}
    </span>
  );
}

function formatDate(iso?: string | null): string {
  if (!iso) return "—";
  return new Intl.DateTimeFormat("vi-VN", { dateStyle: "short", timeStyle: "short" }).format(new Date(iso));
}

/* ── Create Tunnel Dialog ── */
function CreateTunnelDialog({ accountId, onClose }: { accountId: string; onClose: () => void }) {
  const t = useTranslations("cloudflareAccounts");
  const create = useCreateAccountTunnel(accountId);
  const [name, setName] = useState("");
  const [token, setToken] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const handleCreate = async () => {
    const result = await create.mutateAsync(name);
    setToken(result.token);
  };

  const handleCopy = () => {
    if (!token) return;
    navigator.clipboard.writeText(`cloudflared service install ${token}`);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={token ? onClose : undefined} />
      <div className="relative z-10 w-full max-w-lg rounded-3xl border border-border/60 bg-card p-6 shadow-2xl">
        <div className="flex items-center gap-3 mb-6">
          <div className="flex size-10 items-center justify-center rounded-2xl bg-primary/10">
            <Cable className="size-5 text-primary" />
          </div>
          <div>
            <h3 className="text-lg font-bold text-foreground">{t("tunnelForm.createTitle")}</h3>
            <p className="text-xs text-muted-foreground">{t("tunnelForm.createDesc")}</p>
          </div>
        </div>

        {!token ? (
          <>
            <div className="space-y-4">
              <div>
                <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground mb-1.5 block">
                  {t("tunnelForm.name")}
                </label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder={t("tunnelForm.namePlaceholder")}
                  className="w-full rounded-xl border border-border/70 bg-background/90 px-4 py-2.5 text-sm text-foreground placeholder:text-muted-foreground/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary shadow-2xs"
                  autoFocus
                />
              </div>
            </div>

            <div className="mt-6 flex justify-end gap-3">
              <Button variant="outline" size="sm" onClick={onClose} className="rounded-xl">
                {t("form.cancel")}
              </Button>
              <Button
                size="sm"
                onClick={handleCreate}
                disabled={!name.trim() || create.isPending}
                className="gap-2 rounded-xl bg-gradient-to-r from-primary to-primary/80 font-semibold"
              >
                <Plus className="size-4" />
                {create.isPending ? t("form.saving") : t("form.create")}
              </Button>
            </div>
          </>
        ) : (
          <div className="space-y-4">
            <div className="rounded-2xl border border-emerald-500/30 bg-emerald-500/10 p-4">
              <div className="flex items-center gap-2 mb-2">
                <Key className="size-4 text-emerald-600" />
                <span className="text-sm font-bold text-emerald-600 dark:text-emerald-400">{t("tunnelForm.tokenTitle")}</span>
              </div>
              <p className="text-xs text-muted-foreground mb-3">{t("tunnelForm.tokenDesc")}</p>
              <div className="flex items-center gap-2 rounded-xl border border-border/70 bg-background/90 p-3">
                <code className="flex-1 text-xs font-mono break-all text-foreground">
                  cloudflared service install {token}
                </code>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleCopy}
                  className="size-8 shrink-0 p-0 rounded-lg cursor-pointer"
                >
                  {copied ? <Check className="size-4 text-emerald-500" /> : <Copy className="size-4" />}
                </Button>
              </div>
            </div>

            <div className="flex justify-end">
              <Button size="sm" onClick={onClose} className="rounded-xl font-semibold">
                {t("tunnelForm.done")}
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/* ── Main Tab ── */
export function AccountTunnelsTab({ accountId }: { accountId: string }) {
  const t = useTranslations("cloudflareAccounts");
  const { data: tunnels = [], isLoading } = useQuery({
    queryKey: cloudflareAccountsKeys.tunnels(accountId),
    queryFn: () => fetchAccountTunnels(accountId),
  });
  const deleteTunnel = useDeleteAccountTunnel(accountId);
  const [createOpen, setCreateOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);

  if (isLoading) {
    return (
      <div className="space-y-3 py-2">
        <Skeleton className="h-10 w-full rounded-2xl" />
        <Skeleton className="h-14 w-full rounded-2xl" />
        <Skeleton className="h-14 w-full rounded-2xl" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header with Create button */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-sm font-bold text-foreground">
          <Cable className="size-4 text-primary/60" />
          {t("tabs.tunnels")}
          <span className="rounded-full bg-primary/10 px-2 py-0.5 text-xs font-mono text-primary">{tunnels.length}</span>
        </div>
        <Button
          size="sm"
          onClick={() => setCreateOpen(true)}
          className="gap-2 rounded-xl bg-gradient-to-r from-primary to-primary/80 font-semibold text-white shadow-xs"
        >
          <Plus className="size-4" />
          {t("tunnelForm.create")}
        </Button>
      </div>

      {tunnels.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-border/60 bg-muted/20 py-14 text-center">
          <div className="flex size-10 items-center justify-center rounded-xl bg-muted/60 text-muted-foreground mb-2">
            <Cable className="size-5" />
          </div>
          <p className="text-sm font-medium text-muted-foreground">{t("tabs.tunnelsEmpty")}</p>
        </div>
      ) : (
        <div className="overflow-hidden rounded-2xl border border-border/50">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border/50 bg-muted/40">
                <th className="px-4 py-3 text-left font-bold text-xs uppercase tracking-wider text-muted-foreground">{t("tabs.tunnelName")}</th>
                <th className="px-4 py-3 text-left font-bold text-xs uppercase tracking-wider text-muted-foreground">{t("tabs.tunnelStatus")}</th>
                <th className="px-4 py-3 text-left font-bold text-xs uppercase tracking-wider text-muted-foreground">{t("tabs.tunnelType")}</th>
                <th className="px-4 py-3 text-left font-bold text-xs uppercase tracking-wider text-muted-foreground">{t("tabs.tunnelConfig")}</th>
                <th className="px-4 py-3 text-left font-bold text-xs uppercase tracking-wider text-muted-foreground">{t("tabs.tunnelConns")}</th>
                <th className="px-4 py-3 text-left font-bold text-xs uppercase tracking-wider text-muted-foreground">{t("tabs.tunnelCreated")}</th>
                <th className="px-4 py-3 w-12" />
              </tr>
            </thead>
            <tbody className="divide-y divide-border/40">
              {tunnels.map((tunnel) => (
                <tr key={tunnel.id} className="transition-colors hover:bg-muted/30">
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <Cable className="size-4 shrink-0 text-primary/60" />
                      <span className="font-semibold text-foreground truncate max-w-[200px]">{tunnel.name}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <TunnelStatusBadge status={tunnel.status} />
                  </td>
                  <td className="px-4 py-3">
                    <span className="rounded-lg border border-border/70 bg-muted/40 px-2 py-0.5 font-mono text-[11px] text-muted-foreground">
                      {tunnel.tun_type ?? "—"}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <span className="text-xs text-muted-foreground">{tunnel.config_src ?? "—"}</span>
                  </td>
                  <td className="px-4 py-3">
                    <span className="font-mono text-xs text-foreground">{tunnel.connections?.length ?? 0}</span>
                  </td>
                  <td className="px-4 py-3">
                    <span className="text-xs text-muted-foreground">{formatDate(tunnel.created_at)}</span>
                  </td>
                  <td className="px-4 py-3">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setDeleteTarget(tunnel.id)}
                      className="size-8 p-0 rounded-xl text-rose-600 hover:bg-rose-500/10 cursor-pointer"
                      title={t("tunnelForm.delete")}
                    >
                      <Trash2 className="size-3.5" />
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {createOpen && <CreateTunnelDialog accountId={accountId} onClose={() => setCreateOpen(false)} />}

      {deleteTarget !== null && (
        <ConfirmDialog
          isOpen
          onClose={() => setDeleteTarget(null)}
          onConfirm={async () => {
            await deleteTunnel.mutateAsync(deleteTarget);
            setDeleteTarget(null);
          }}
          title={t("tunnelForm.deleteConfirmTitle")}
          description={t("tunnelForm.deleteConfirmDesc")}
          variant="destructive"
          isLoading={deleteTunnel.isPending}
        />
      )}
    </div>
  );
}
