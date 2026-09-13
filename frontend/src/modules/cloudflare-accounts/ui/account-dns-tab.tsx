"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { Globe, Plus, Pencil, Trash2, Shield, ShieldOff } from "lucide-react";
import {
  fetchAccountZones,
  fetchAccountZoneDnsRecords,
  cloudflareAccountsKeys,
  type CfDnsRecord,
  type CfZone,
} from "@/entities/cloudflare-account";
import { Button } from "@/shared/ui/button";
import { Skeleton } from "@/shared/ui/skeleton";
import { ConfirmDialog } from "@/shared/ui/confirm-dialog";
import { Can } from "@/entities/permission";
import { ACTIONS, PERMISSIONS } from "@/shared/constants/permissions";
import { DNS_TYPE_COLORS, isDnsType } from "../model/dns";
import { DnsRecordFormDialog } from "./dns-record-form-dialog";
import { useDeleteAccountDnsRecord } from "../hooks/use-account-mutations";

function DnsTypeBadge({ type }: { type: string }) {
  const color = isDnsType(type) ? DNS_TYPE_COLORS[type] : "border-border/70 bg-muted/40 text-muted-foreground";
  return (
    <span className={`inline-flex items-center rounded-lg border px-2 py-0.5 font-mono text-[11px] font-bold ${color}`}>
      {type}
    </span>
  );
}

function formatTtl(ttl: number): string {
  if (ttl === 1) return "Auto";
  if (ttl < 60) return `${ttl}s`;
  if (ttl < 3600) return `${Math.round(ttl / 60)}m`;
  if (ttl < 86400) return `${Math.round(ttl / 3600)}h`;
  return `${Math.round(ttl / 86400)}d`;
}

/* ── DNS Records Table per zone ── */
function DnsRecordsTable({ accountId, zoneId }: { accountId: string; zoneId: string }) {
  const t = useTranslations("cloudflareAccounts");
  const { data: records = [], isLoading } = useQuery({
    queryKey: cloudflareAccountsKeys.zoneDnsRecords(accountId, zoneId),
    queryFn: () => fetchAccountZoneDnsRecords(accountId, zoneId),
    enabled: !!zoneId,
  });
  const deleteDns = useDeleteAccountDnsRecord(accountId, zoneId);
  const [createOpen, setCreateOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<CfDnsRecord | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);

  if (isLoading) {
    return (
      <div className="space-y-3 py-2">
        <Skeleton className="h-10 w-full rounded-2xl" />
        <Skeleton className="h-12 w-full rounded-2xl" />
        <Skeleton className="h-12 w-full rounded-2xl" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Header with Add button */}
      <div className="flex items-center justify-end">
        <Button
          size="sm"
          onClick={() => setCreateOpen(true)}
          className="gap-2 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 font-semibold text-white shadow-xs"
        >
          <Plus className="size-4" />
          {t("dnsForm.create")}
        </Button>
      </div>

      {records.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-border/60 bg-muted/20 py-10 text-center">
          <p className="text-sm text-muted-foreground">{t("tabs.dnsEmpty")}</p>
        </div>
      ) : (
        <div className="overflow-hidden rounded-2xl border border-border/50">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border/50 bg-muted/40">
                <th className="px-4 py-3 text-left font-bold text-xs uppercase tracking-wider text-muted-foreground">{t("tabs.dnsType")}</th>
                <th className="px-4 py-3 text-left font-bold text-xs uppercase tracking-wider text-muted-foreground">{t("tabs.dnsName")}</th>
                <th className="px-4 py-3 text-left font-bold text-xs uppercase tracking-wider text-muted-foreground">{t("tabs.dnsContent")}</th>
                <th className="px-4 py-3 text-left font-bold text-xs uppercase tracking-wider text-muted-foreground">TTL</th>
                <th className="px-4 py-3 text-left font-bold text-xs uppercase tracking-wider text-muted-foreground">{t("tabs.dnsProxy")}</th>
                <th className="px-4 py-3 w-20" />
              </tr>
            </thead>
            <tbody className="divide-y divide-border/40">
              {records.map((record) => (
                <tr key={record.id} className="transition-colors hover:bg-muted/30 group">
                  <td className="px-4 py-3">
                    <DnsTypeBadge type={record.type} />
                  </td>
                  <td className="px-4 py-3">
                    <span className="font-semibold text-foreground text-xs truncate max-w-[200px] block">{record.name}</span>
                  </td>
                  <td className="px-4 py-3">
                    <span className="font-mono text-xs text-muted-foreground truncate max-w-[250px] block">{record.content}</span>
                  </td>
                  <td className="px-4 py-3">
                    <span className="rounded-lg border border-border/70 bg-muted/40 px-2 py-0.5 font-mono text-[11px] text-muted-foreground">
                      {formatTtl(record.ttl)}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    {record.proxied ? (
                      <Shield className="size-4 text-amber-500" />
                    ) : (
                      <ShieldOff className="size-4 text-muted-foreground/50" />
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-1">
                      <Can I={ACTIONS.UPDATE} a={PERMISSIONS.CLOUDFLARE_DNS.RESOURCE}>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setEditTarget(record)}
                          className="size-7 p-0 rounded-lg text-blue-600 hover:bg-blue-500/10 cursor-pointer"
                          title="Edit"
                        >
                          <Pencil className="size-3" />
                        </Button>
                      </Can>
                      <Can I={ACTIONS.DELETE} a={PERMISSIONS.CLOUDFLARE_DNS.RESOURCE}>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setDeleteTarget(record.id)}
                          className="size-7 p-0 rounded-lg text-rose-600 hover:bg-rose-500/10 cursor-pointer"
                          title="Delete"
                        >
                          <Trash2 className="size-3" />
                        </Button>
                      </Can>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {createOpen && (
        <DnsRecordFormDialog accountId={accountId} zoneId={zoneId} onClose={() => setCreateOpen(false)} />
      )}

      {editTarget && (
        <DnsRecordFormDialog
          accountId={accountId}
          zoneId={zoneId}
          record={editTarget}
          onClose={() => setEditTarget(null)}
        />
      )}

      {deleteTarget !== null && (
        <ConfirmDialog
          isOpen
          onClose={() => setDeleteTarget(null)}
          onConfirm={async () => {
            await deleteDns.mutateAsync(deleteTarget);
            setDeleteTarget(null);
          }}
          title={t("dnsForm.deleteConfirmTitle")}
          description={t("dnsForm.deleteConfirmDesc")}
          variant="destructive"
          isLoading={deleteDns.isPending}
        />
      )}
    </div>
  );
}

/* ── Zone Selector ── */
function ZoneSelector({
  zones,
  selected,
  onSelect,
}: {
  zones: CfZone[];
  selected: string;
  onSelect: (zoneId: string) => void;
}) {
  return (
    <div className="flex flex-wrap gap-2 mb-4">
      {zones.map((zone) => (
        <button
          key={zone.id}
          type="button"
          onClick={() => onSelect(zone.id)}
          className={`flex items-center gap-1.5 rounded-xl border px-3 py-1.5 text-sm font-semibold transition-all cursor-pointer ${
            selected === zone.id
              ? "border-primary/50 bg-primary/10 text-primary shadow-sm"
              : "border-border/60 bg-card/80 text-muted-foreground hover:border-primary/30 hover:text-foreground"
          }`}
        >
          <Globe className="size-3.5" />
          {zone.name}
        </button>
      ))}
    </div>
  );
}

/* ── Main Tab ── */
export function AccountDnsTab({ accountId }: { accountId: string }) {
  const t = useTranslations("cloudflareAccounts");
  const { data: zones = [], isLoading: zonesLoading } = useQuery({
    queryKey: cloudflareAccountsKeys.zones(accountId),
    queryFn: () => fetchAccountZones(accountId),
  });

  const [selectedZone, setSelectedZone] = useState<string>("");
  const activeZone = selectedZone || zones[0]?.id || "";

  if (zonesLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <div className="size-6 animate-spin rounded-full border-2 border-primary border-t-transparent" />
      </div>
    );
  }

  if (zones.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-border/60 bg-muted/20 py-14 text-center">
        <div className="flex size-10 items-center justify-center rounded-xl bg-muted/60 text-muted-foreground mb-2">
          <Globe className="size-5" />
        </div>
        <p className="text-sm font-medium text-muted-foreground">{t("tabs.noZones")}</p>
      </div>
    );
  }

  return (
    <div>
      {zones.length > 1 && (
        <ZoneSelector zones={zones} selected={activeZone} onSelect={setSelectedZone} />
      )}
      {zones.length === 1 && (
        <div className="mb-4 flex items-center gap-2 text-sm font-semibold text-foreground">
          <Globe className="size-4 text-primary/60" />
          {zones[0].name}
        </div>
      )}
      {activeZone && <DnsRecordsTable accountId={accountId} zoneId={activeZone} />}
    </div>
  );
}
