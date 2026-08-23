"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { X, Plus } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/input";
import { Label } from "@/shared/ui/label";
import { useApiErrorMessage } from "@/shared/lib/handle-api-error";
import { DNS_RECORD_TYPES, type DnsRecord, type DnsRecordType } from "../model/schema";
import { useCreateDnsRecord, useUpdateDnsRecord } from "../hooks/use-dns-records";

interface DnsRecordFormDialogProps {
  environmentId: string;
  record: DnsRecord | null;
  onClose: () => void;
}

function initialFormState(record: DnsRecord | null) {
  return {
    recordType: (record?.recordType ?? "A") as DnsRecordType,
    name: record?.name ?? "",
    content: record?.content ?? "",
    priority: record?.priority?.toString() ?? "",
    proxied: record?.proxied ?? false,
    ttl: record?.ttl ?? 1,
  };
}

function submitLabel(t: ReturnType<typeof useTranslations>, isSaving: boolean, isEditing: boolean): string {
  if (isSaving) return t("form.saving");
  return isEditing ? t("form.save") : t("form.create");
}

function RecordTypeField({
  recordType,
  onChange,
  isEditing,
}: {
  recordType: DnsRecordType;
  onChange: (type: DnsRecordType) => void;
  isEditing: boolean;
}) {
  const t = useTranslations("cloudflareDns");
  return (
    <div className="space-y-1.5">
      <Label htmlFor="record-type">{t("records.type")}</Label>
      <select
        id="record-type"
        value={recordType}
        onChange={(event) => onChange(event.target.value as DnsRecordType)}
        disabled={isEditing}
        aria-describedby={isEditing ? "record-type-hint" : undefined}
        className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
      >
        {DNS_RECORD_TYPES.map((type) => (
          <option key={type} value={type}>
            {type}
          </option>
        ))}
      </select>
      {isEditing ? (
        <p id="record-type-hint" className="text-xs text-muted-foreground">
          {t("records.typeImmutableHint")}
        </p>
      ) : null}
    </div>
  );
}

function RecordPriorityField({
  priority,
  onChange,
}: {
  priority: string;
  onChange: (value: string) => void;
}) {
  const t = useTranslations("cloudflareDns");
  return (
    <div className="space-y-1.5">
      <Label htmlFor="record-priority">{t("records.priority")}</Label>
      <Input
        id="record-priority"
        type="number"
        value={priority}
        onChange={(event) => onChange(event.target.value)}
        required
        aria-describedby="record-priority-hint"
      />
      <p id="record-priority-hint" className="text-xs text-muted-foreground">
        {t("records.priorityHint")}
      </p>
    </div>
  );
}

export function DnsRecordFormDialog({ environmentId, record, onClose }: DnsRecordFormDialogProps) {
  const t = useTranslations("cloudflareDns");
  const getErrorMessage = useApiErrorMessage("cloudflareDns");
  const isEditing = Boolean(record);
  const initial = initialFormState(record);

  const [recordType, setRecordType] = useState<DnsRecordType>(initial.recordType);
  const [name, setName] = useState(initial.name);
  const [content, setContent] = useState(initial.content);
  const [priority, setPriority] = useState<string>(initial.priority);
  const [proxied, setProxied] = useState(initial.proxied);
  const [ttl, setTtl] = useState(initial.ttl);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const create = useCreateDnsRecord(environmentId);
  const update = useUpdateDnsRecord(environmentId);
  const isSaving = create.isPending || update.isPending;
  const requiresPriority = recordType === "MX";

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    setErrorMessage(null);
    const parsedPriority = requiresPriority ? Number(priority) : null;
    const callbacks = {
      onSuccess: () => onClose(),
      onError: (err: unknown) => setErrorMessage(getErrorMessage(err)),
    };
    if (isEditing && record) {
      update.mutate(
        { recordId: record.id, data: { content, priority: parsedPriority, proxied, ttl } },
        callbacks,
      );
    } else {
      create.mutate({ recordType, name, content, priority: parsedPriority, proxied, ttl }, callbacks);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 animate-in fade-in-0"
      role="dialog"
      aria-modal="true"
      aria-labelledby="dns-record-form-title"
    >
      <div className="w-full max-w-md rounded-lg border border-border bg-background p-6 shadow-lg animate-in zoom-in-95">
        <div className="flex items-center justify-between mb-4">
          <h2 id="dns-record-form-title" className="text-lg font-semibold">
            {isEditing ? t("records.editRecord") : t("records.createRecord")}
          </h2>
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={onClose}
            aria-label={t("form.cancel")}
            className="focus-visible:ring-2 focus-visible:ring-primary"
          >
            <X className="size-4" aria-hidden="true" />
          </Button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          {errorMessage && (
            <div role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {errorMessage}
            </div>
          )}

          <RecordTypeField recordType={recordType} onChange={setRecordType} isEditing={isEditing} />

          <div className="space-y-1.5">
            <Label htmlFor="record-name">{t("records.name")}</Label>
            <Input
              id="record-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              disabled={isEditing}
              required
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="record-content">{t("records.content")}</Label>
            <Input
              id="record-content"
              value={content}
              onChange={(event) => setContent(event.target.value)}
              required
            />
          </div>

          {requiresPriority ? <RecordPriorityField priority={priority} onChange={setPriority} /> : null}

          <div className="flex items-center gap-2">
            <input
              id="record-proxied"
              type="checkbox"
              checked={proxied}
              onChange={(event) => setProxied(event.target.checked)}
              className="size-4 rounded border-input focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
            />
            <Label htmlFor="record-proxied" className="cursor-pointer">
              {t("records.proxied")}
            </Label>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="record-ttl">{t("records.ttl")}</Label>
            <Input
              id="record-ttl"
              type="number"
              min={1}
              value={ttl}
              onChange={(event) => setTtl(Number(event.target.value))}
              required
            />
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <Button type="button" variant="outline" onClick={onClose}>
              {t("form.cancel")}
            </Button>
            <Button type="submit" disabled={isSaving}>
              <Plus className="mr-1 size-3.5" aria-hidden="true" />
              {submitLabel(t, isSaving, isEditing)}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
