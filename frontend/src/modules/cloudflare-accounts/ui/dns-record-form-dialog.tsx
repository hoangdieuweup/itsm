"use client";

import { useState } from "react";
import { createPortal } from "react-dom";
import { useTranslations } from "next-intl";
import { Globe, Plus, Pencil, Shield, ShieldOff } from "lucide-react";
import type { CfDnsRecord } from "@/entities/cloudflare-account";
import { Button } from "@/shared/ui/button";
import { useIsMounted } from "@/shared/hooks/use-is-mounted";
import {
  DNS_TYPES,
  DNS_TYPE_COLORS,
  contentPlaceholderFor,
  hasPriority,
  isProxyable,
} from "../model/dns";
import {
  useCreateAccountDnsRecord,
  useUpdateAccountDnsRecord,
} from "../hooks/use-account-mutations";

const FIELD_CLASS =
  "w-full rounded-xl border border-border/70 bg-background/90 px-4 py-2.5 text-sm text-foreground placeholder:text-muted-foreground/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary shadow-2xs";
const LABEL_CLASS =
  "text-xs font-bold uppercase tracking-wider text-muted-foreground mb-1.5 block";

const TTL_OPTIONS = [
  { value: 1, label: "Auto" },
  { value: 60, label: "1 min" },
  { value: 120, label: "2 min" },
  { value: 300, label: "5 min" },
  { value: 600, label: "10 min" },
  { value: 900, label: "15 min" },
  { value: 1800, label: "30 min" },
  { value: 3600, label: "1 hour" },
  { value: 7200, label: "2 hours" },
  { value: 18000, label: "5 hours" },
  { value: 43200, label: "12 hours" },
  { value: 86400, label: "1 day" },
] as const;

interface DnsFormData {
  record_type: string;
  name: string;
  content: string;
  ttl: number;
  proxied: boolean;
  priority: number | undefined;
}

function useDnsRecordForm({
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
  const isEditing = Boolean(record);
  const createDns = useCreateAccountDnsRecord(accountId, zoneId);
  const updateDns = useUpdateAccountDnsRecord(accountId, zoneId);

  const [formData, setFormData] = useState<DnsFormData>({
    record_type: record?.type ?? "A",
    name: record?.name ?? "",
    content: record?.content ?? "",
    ttl: record?.ttl ?? 1,
    proxied: record?.proxied ?? false,
    priority: record?.type === "MX" ? 10 : undefined,
  });

  const patch = (changes: Partial<DnsFormData>) =>
    setFormData((current) => ({ ...current, ...changes }));

  const handleSubmit = async () => {
    if (isEditing && record) {
      await updateDns.mutateAsync({ cfRecordId: record.id, ...formData });
    } else {
      await createDns.mutateAsync(formData);
    }
    onClose();
  };

  return {
    formData,
    patch,
    handleSubmit,
    isEditing,
    isPending: createDns.isPending || updateDns.isPending,
    canSubmit: Boolean(formData.name.trim()) && Boolean(formData.content.trim()),
  };
}

function DnsTypeSelector({
  value,
  onChange,
  disabled,
}: {
  value: string;
  onChange: (recordType: string) => void;
  disabled: boolean;
}) {
  const t = useTranslations("cloudflareAccounts");

  return (
    <div>
      <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground mb-2 block">
        {t("tabs.dnsType")}
      </label>
      <div className="flex flex-wrap gap-1.5">
        {DNS_TYPES.map((type) => (
          <button
            key={type}
            type="button"
            onClick={() => onChange(type)}
            disabled={disabled}
            className={`rounded-xl border px-3 py-1.5 font-mono text-xs font-bold transition-all cursor-pointer disabled:cursor-not-allowed disabled:opacity-50 ${
              value === type
                ? DNS_TYPE_COLORS[type]
                : "border-border/60 bg-card/80 text-muted-foreground hover:border-primary/30"
            }`}
          >
            {type}
          </button>
        ))}
      </div>
    </div>
  );
}

function DnsTtlSelect({ value, onChange }: { value: number; onChange: (ttl: number) => void }) {
  return (
    <div>
      <label className={LABEL_CLASS}>TTL</label>
      <select
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className={`${FIELD_CLASS} cursor-pointer`}
      >
        {TTL_OPTIONS.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </div>
  );
}

function DnsProxyToggle({
  proxied,
  onToggle,
}: {
  proxied: boolean;
  onToggle: () => void;
}) {
  const t = useTranslations("cloudflareAccounts");

  return (
    <div className="flex items-center justify-between rounded-2xl border border-border/60 bg-muted/20 p-4">
      <div className="flex items-center gap-3">
        {proxied ? (
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
        aria-checked={proxied}
        onClick={onToggle}
        className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors cursor-pointer ${
          proxied ? "bg-amber-500" : "bg-border"
        }`}
      >
        <span
          className={`inline-block size-4 rounded-full bg-white shadow-sm transition-transform ${
            proxied ? "translate-x-6" : "translate-x-1"
          }`}
        />
      </button>
    </div>
  );
}

function DnsFormActions({
  isEditing,
  isPending,
  canSubmit,
  onSubmit,
  onClose,
}: {
  isEditing: boolean;
  isPending: boolean;
  canSubmit: boolean;
  onSubmit: () => void;
  onClose: () => void;
}) {
  const t = useTranslations("cloudflareAccounts");
  const submitLabel = isPending ? t("form.saving") : isEditing ? t("form.save") : t("form.create");

  return (
    <div className="mt-6 flex justify-end gap-3">
      <Button variant="outline" size="sm" onClick={onClose} className="rounded-xl">
        {t("form.cancel")}
      </Button>
      <Button
        size="sm"
        onClick={onSubmit}
        disabled={!canSubmit || isPending}
        className="gap-2 rounded-xl bg-gradient-to-r from-blue-600 to-indigo-600 font-semibold text-white shadow-xs"
      >
        {isEditing ? <Pencil className="size-4" /> : <Plus className="size-4" />}
        {submitLabel}
      </Button>
    </div>
  );
}

function DnsFormHeader({ isEditing }: { isEditing: boolean }) {
  const t = useTranslations("cloudflareAccounts");

  return (
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
  );
}

export function DnsRecordFormDialog({
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
  const { formData, patch, handleSubmit, isEditing, isPending, canSubmit } = useDnsRecordForm({
    accountId,
    zoneId,
    record,
    onClose,
  });

  if (!isMounted) return null;

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/50 backdrop-blur-sm" onClick={onClose} />
      <div className="relative z-10 w-full max-w-lg rounded-3xl border border-border/60 bg-card p-6 shadow-2xl">
        <DnsFormHeader isEditing={isEditing} />

        <div className="space-y-4">
          <DnsTypeSelector
            value={formData.record_type}
            onChange={(record_type) => patch({ record_type })}
            disabled={isEditing}
          />

          <div>
            <label className={LABEL_CLASS}>{t("tabs.dnsName")}</label>
            <input
              type="text"
              value={formData.name}
              onChange={(e) => patch({ name: e.target.value })}
              placeholder="@"
              className={FIELD_CLASS}
            />
          </div>

          <div>
            <label className={LABEL_CLASS}>{t("tabs.dnsContent")}</label>
            <input
              type="text"
              value={formData.content}
              onChange={(e) => patch({ content: e.target.value })}
              placeholder={contentPlaceholderFor(formData.record_type)}
              className={`${FIELD_CLASS} font-mono`}
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <DnsTtlSelect value={formData.ttl} onChange={(ttl) => patch({ ttl })} />

            {hasPriority(formData.record_type) && (
              <div>
                <label className={LABEL_CLASS}>Priority</label>
                <input
                  type="number"
                  value={formData.priority ?? 10}
                  onChange={(e) => patch({ priority: Number(e.target.value) })}
                  min={0}
                  max={65535}
                  className={`${FIELD_CLASS} font-mono`}
                />
              </div>
            )}
          </div>

          {isProxyable(formData.record_type) && (
            <DnsProxyToggle
              proxied={formData.proxied}
              onToggle={() => patch({ proxied: !formData.proxied })}
            />
          )}
        </div>

        <DnsFormActions
          isEditing={isEditing}
          isPending={isPending}
          canSubmit={canSubmit}
          onSubmit={handleSubmit}
          onClose={onClose}
        />
      </div>
    </div>,
    document.body,
  );
}
