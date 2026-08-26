"use client";

import { useState, useCallback, useSyncExternalStore } from "react";
import { createPortal } from "react-dom";
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
import { ConfirmDialog } from "@/shared/ui/confirm-dialog";
import { Can } from "@/entities/permission";
import { ACTIONS, PERMISSIONS } from "@/shared/constants/permissions";
import {
  useCreateAccountDnsRecord,
  useUpdateAccountDnsRecord,
  useDeleteAccountDnsRecord,
} from "../hooks/use-account-mutations";

const DNS_TYPES = ["A", "AAAA", "CNAME", "MX", "TXT", "NS", "SRV", "CAA", "HTTPS"] as const;

const DNS_TYPE_COLORS: Record<string, string> = {
  A: "border-emerald-500/30 bg-emerald-500/15 text-emerald-600 dark:text-emerald-400",
  AAAA: "border-teal-500/30 bg-teal-500/15 text-teal-600 dark:text-teal-400",
  CNAME: "border-blue-500/30 bg-blue-500/15 text-blue-600 dark:text-blue-400",
  MX: "border-purple-500/30 bg-purple-500/15 text-purple-600 dark:text-purple-400",
  TXT: "border-gray-500/30 bg-gray-500/15 text-gray-600 dark:text-gray-400",
  NS: "border-amber-500/30 bg-amber-500/15 text-amber-600 dark:text-amber-400",
  SRV: "border-pink-500/30 bg-pink-500/15 text-pink-600 dark:text-pink-400",
  CAA: "border-red-500/30 bg-red-500/15 text-red-600 dark:text-red-400",
};

function DnsTypeBadge({ type }: { type: string }) {
  const color = DNS_TYPE_COLORS[type] ?? "border-border/70 bg-muted/40 text-muted-foreground";
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

/* ── Hydration-safe mount check ── */
const emptySubscribe = () => () => {};
const useIsMounted = () =>
  useSyncExternalStore(
    emptySubscribe,
    () => true,
    () => false,
  );

/* ── DNS Record Form Dialog ── */
function DnsRecordFormDialog({
  accountId,
  zoneId,
  record,
  onClose,
}: {
  accountId: string;
  zoneId: string;
  record?: CfDnsRecord | null;
  onClose: () => void;
}) {
  const t = useTranslations("cloudflareAccounts");
  const isMounted = useIsMounted();
  const isEditing = Boolean(record);
  const createDns = useCreateAccountDnsRecord(accountId, zoneId);
  const updateDns = useUpdateAccountDnsRecord(accountId, zoneId);

  const [formData, setFormData] = useState({
    record_type: record?.type ?? "A",
    name: record?.name ?? "",
    content: record?.content ?? "",
    ttl: record?.ttl ?? 1,
    proxied: record?.proxied ?? false,
    priority: (record?.type === "MX" ? 10 : undefined) as number | undefined,
  });

  const handleSubmit = async () => {
    if (isEditing && record) {
      await updateDns.mutateAsync({
        cfRecordId: record.id,
        ...formData,
      });
    } else {
      await createDns.mutateAsync(formData);
    }
    onClose();
  };

  const isPending = createDns.isPending || updateDns.isPending;
  const showPriority = formData.record_type === "MX" || formData.record_type === "SRV";

  if (!isMounted) return null;

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={onClose} />
      <div className="relative z-10 w-full max-w-lg rounded-3xl border border-border/60 bg-card p-6 shadow-2xl">
        <div className="flex items-center gap-3 mb-6">
          <div className="flex size-10 items-center justify-center rounded-2xl bg-blue-500/10">
            <Globe className="size-5 text-blue-600 dark:text-blue-400" />
          </div>
          <div>
            <h3 className="text-lg font-bold text-foreground">
              {isEditing ? t("dnsForm.editTitle") : t("dnsForm.createTitle")}
            </h3>
            <p className="text-xs text-muted-foreground">{t("dnsForm.desc")}</p>
          </div>
        </div>

        <div className="space-y-4">
          {/* Type selector — Cloudflare-style pill buttons */}
          <div>
            <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground mb-2 block">
              {t("tabs.dnsType")}
            </label>
            <div className="flex flex-wrap gap-1.5">
              {DNS_TYPES.map((type) => (
                <button
                  key={type}
                  type="button"
                  onClick={() => setFormData((d) => ({ ...d, record_type: type }))}
                  disabled={isEditing}
                  className={`rounded-xl border px-3 py-1.5 font-mono text-xs font-bold transition-all cursor-pointer disabled:cursor-not-allowed disabled:opacity-50 ${
                    formData.record_type === type
                      ? DNS_TYPE_COLORS[type] ?? "border-primary/50 bg-primary/10 text-primary"
                      : "border-border/60 bg-card/80 text-muted-foreground hover:border-primary/30"
                  }`}
                >
                  {type}
                </button>
              ))}
            </div>
          </div>

          {/* Name */}
          <div>
            <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground mb-1.5 block">
              {t("tabs.dnsName")}
            </label>
            <input
              type="text"
              value={formData.name}
              onChange={(e) => setFormData((d) => ({ ...d, name: e.target.value }))}
              placeholder="@"
              className="w-full rounded-xl border border-border/70 bg-background/90 px-4 py-2.5 text-sm text-foreground placeholder:text-muted-foreground/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary shadow-2xs"
            />
          </div>

          {/* Content */}
          <div>
            <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground mb-1.5 block">
              {t("tabs.dnsContent")}
            </label>
            <input
              type="text"
              value={formData.content}
              onChange={(e) => setFormData((d) => ({ ...d, content: e.target.value }))}
              placeholder={formData.record_type === "A" ? "192.0.2.1" : formData.record_type === "CNAME" ? "example.com" : ""}
              className="w-full rounded-xl border border-border/70 bg-background/90 px-4 py-2.5 text-sm font-mono text-foreground placeholder:text-muted-foreground/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary shadow-2xs"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            {/* TTL */}
            <div>
              <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground mb-1.5 block">
                TTL
              </label>
              <select
                value={formData.ttl}
                onChange={(e) => setFormData((d) => ({ ...d, ttl: Number(e.target.value) }))}
                className="w-full rounded-xl border border-border/70 bg-background/90 px-4 py-2.5 text-sm text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary shadow-2xs cursor-pointer"
              >
                <option value={1}>Auto</option>
                <option value={60}>1 min</option>
                <option value={120}>2 min</option>
                <option value={300}>5 min</option>
                <option value={600}>10 min</option>
                <option value={900}>15 min</option>
                <option value={1800}>30 min</option>
                <option value={3600}>1 hour</option>
                <option value={7200}>2 hours</option>
                <option value={18000}>5 hours</option>
                <option value={43200}>12 hours</option>
                <option value={86400}>1 day</option>
              </select>
            </div>

            {/* Priority (MX/SRV only) */}
            {showPriority && (
              <div>
                <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground mb-1.5 block">
                  Priority
                </label>
                <input
                  type="number"
                  value={formData.priority ?? 10}
                  onChange={(e) => setFormData((d) => ({ ...d, priority: Number(e.target.value) }))}
                  min={0}
                  max={65535}
                  className="w-full rounded-xl border border-border/70 bg-background/90 px-4 py-2.5 text-sm font-mono text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary shadow-2xs"
                />
              </div>
            )}
          </div>

          {/* Proxied toggle — Cloudflare orange-cloud style */}
          {(formData.record_type === "A" || formData.record_type === "AAAA" || formData.record_type === "CNAME") && (
            <div className="flex items-center justify-between rounded-2xl border border-border/60 bg-muted/20 p-4">
              <div className="flex items-center gap-3">
                {formData.proxied ? (
                  <Shield className="size-5 text-amber-500" />
                ) : (
                  <ShieldOff className="size-5 text-muted-foreground/50" />
                )}
                <div>
                  <p className="text-sm font-semibold text-foreground">{t("dnsForm.proxy")}</p>
                  <p className="text-xs text-muted-foreground">{t("dnsForm.proxyDesc")}</p>
                </div>
              </div>
              <button
                type="button"
                role="switch"
                aria-checked={formData.proxied}
                onClick={() => setFormData((d) => ({ ...d, proxied: !d.proxied }))}
                className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors cursor-pointer ${
                  formData.proxied ? "bg-amber-500" : "bg-border"
                }`}
              >
                <span
                  className={`inline-block size-4 rounded-full bg-white shadow-sm transition-transform ${
                    formData.proxied ? "translate-x-6" : "translate-x-1"
                  }`}
                />
              </button>
            </div>
          )}
        </div>

        <div className="mt-6 flex justify-end gap-3">
          <Button variant="outline" size="sm" onClick={onClose} className="rounded-xl">
            {t("form.cancel")}
          </Button>
          <Button
            size="sm"
            onClick={handleSubmit}
            disabled={!formData.name.trim() || !formData.content.trim() || isPending}
            className="gap-2 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 font-semibold text-white shadow-xs"
          >
            {isEditing ? <Pencil className="size-4" /> : <Plus className="size-4" />}
            {isPending ? t("form.saving") : isEditing ? t("form.save") : t("form.create")}
          </Button>
        </div>
      </div>
    </div>,
    document.body,
  );
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
      <div className="flex items-center justify-center py-12">
        <div className="size-5 animate-spin rounded-full border-2 border-primary border-t-transparent" />
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
