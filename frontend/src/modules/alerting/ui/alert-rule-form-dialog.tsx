"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Plus } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/input";
import { Label } from "@/shared/ui/label";
import { Dialog, DialogErrorAlert } from "@/shared/ui/dialog";
import { useApiErrorMessage } from "@/shared/lib/handle-api-error";
import { useCloudflareConfigQuery } from "@/entities/cloudflare-config";
import { ALERT_SEVERITY } from "@/entities/incident";
import { ALERT_RULE_SOURCE, type AlertRule, type AlertRuleSource } from "../model/schema";
import { type AlertRuleFormValues } from "../api/fetchers";
import { useAvailableAlertsQuery } from "../hooks/use-alert-rules";
import { useCreateAlertRule } from "../hooks/use-create-alert-rule";
import { useUpdateAlertRule } from "../hooks/use-update-alert-rule";
import { ChannelMultiselect } from "./channel-multiselect";
import { IconNotification } from "@/shared/ui/icons";

interface AlertRuleFormDialogProps {
  environmentId: string;
  projectId: string;
  alertRule: AlertRule | null;
  onClose: () => void;
}

interface AlertRuleFormFields {
  name: string;
  source: AlertRuleSource;
  cfAlertType: string;
  endpointUrl: string;
  query: string;
  forDuration: string;
  severity: string;
  channelIds: string[];
}

function stringField(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

const EMPTY_FIELDS: AlertRuleFormFields = {
  name: "",
  source: ALERT_RULE_SOURCE.CLOUDFLARE_NATIVE,
  cfAlertType: "",
  endpointUrl: "",
  query: "",
  forDuration: "5m",
  severity: ALERT_SEVERITY.MEDIUM,
  channelIds: [],
};

function computeInitialFields(alertRule: AlertRule | null): AlertRuleFormFields {
  if (!alertRule) return EMPTY_FIELDS;

  const condition = alertRule.condition ?? {};
  return {
    name: alertRule.name,
    source: alertRule.source,
    cfAlertType: alertRule.cfAlertType ?? "",
    endpointUrl: stringField(condition.endpoint_url),
    query: stringField(condition.query),
    forDuration: stringField(condition.for, "5m"),
    severity: alertRule.severity,
    channelIds: alertRule.channelIds,
  };
}

function useAlertRuleFormFields(alertRule: AlertRule | null): {
  fields: AlertRuleFormFields;
  setField: <K extends keyof AlertRuleFormFields>(key: K, value: AlertRuleFormFields[K]) => void;
} {
  const [fields, setFields] = useState<AlertRuleFormFields>(() => computeInitialFields(alertRule));

  function setField<K extends keyof AlertRuleFormFields>(key: K, value: AlertRuleFormFields[K]) {
    setFields((current) => ({ ...current, [key]: value }));
  }

  return { fields, setField };
}

function buildCreatePayload(fields: AlertRuleFormFields): AlertRuleFormValues {
  return {
    name: fields.name,
    source: fields.source,
    cfAlertType: fields.source === ALERT_RULE_SOURCE.CLOUDFLARE_NATIVE ? fields.cfAlertType : null,
    condition:
      fields.source === ALERT_RULE_SOURCE.LOKI_QUERY
        ? { endpoint_url: fields.endpointUrl, query: fields.query, for: fields.forDuration }
        : null,
    severity: fields.severity,
    channelIds: fields.channelIds,
  };
}

function submitLabel(t: ReturnType<typeof useTranslations>, isSaving: boolean, isEditing: boolean): string {
  if (isSaving) return t("form.saving");
  return isEditing ? t("form.save") : t("form.create");
}

function CloudflareNativeFields({
  environmentId,
  cfAlertType,
  onChange,
}: {
  environmentId: string;
  cfAlertType: string;
  onChange: (value: string) => void;
}) {
  const t = useTranslations("alerting");
  const { data: config } = useCloudflareConfigQuery(environmentId);
  const accountId = config?.cloudflareAccountId ?? null;
  const { data: options, isLoading } = useAvailableAlertsQuery(accountId);

  if (!accountId) {
    return <p className="text-sm text-muted-foreground">{t("fields.cloudflareNotBoundHint")}</p>;
  }

  return (
    <div className="space-y-1.5">
      <Label htmlFor="alert-rule-cf-type">{t("fields.cfAlertType")}</Label>
      <select
        id="alert-rule-cf-type"
        value={cfAlertType}
        onChange={(event) => onChange(event.target.value)}
        disabled={isLoading}
        required
        className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
      >
        <option value="" disabled>
          {isLoading ? t("fields.cfAlertTypeLoading") : t("fields.cfAlertTypePlaceholder")}
        </option>
        {options?.map((option) => (
          <option key={option.alertType} value={option.alertType}>
            {option.displayName}
          </option>
        ))}
      </select>
    </div>
  );
}

function LokiQueryFields({
  endpointUrl,
  onEndpointUrlChange,
  query,
  onQueryChange,
  forDuration,
  onForDurationChange,
}: {
  endpointUrl: string;
  onEndpointUrlChange: (value: string) => void;
  query: string;
  onQueryChange: (value: string) => void;
  forDuration: string;
  onForDurationChange: (value: string) => void;
}) {
  const t = useTranslations("alerting");
  return (
    <>
      <div className="space-y-1.5">
        <Label htmlFor="alert-rule-endpoint-url">{t("fields.lokiEndpointUrl")}</Label>
        <Input
          id="alert-rule-endpoint-url"
          value={endpointUrl}
          onChange={(event) => onEndpointUrlChange(event.target.value)}
          placeholder="http://loki:3100"
          required
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="alert-rule-query">{t("fields.lokiQuery")}</Label>
        <textarea
          id="alert-rule-query"
          value={query}
          onChange={(event) => onQueryChange(event.target.value)}
          rows={3}
          aria-describedby="alert-rule-query-hint"
          className="w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          required
        />
        <p id="alert-rule-query-hint" className="text-xs text-muted-foreground">
          {t("fields.lokiQueryHint")}
        </p>
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="alert-rule-for">{t("fields.lokiFor")}</Label>
        <Input
          id="alert-rule-for"
          value={forDuration}
          onChange={(event) => onForDurationChange(event.target.value)}
          placeholder="5m"
          required
        />
      </div>
    </>
  );
}

/**
 * Source/condition fields are creation-time-only: the backend's
 * AlertRuleUpdate schema accepts neither source nor cfAlertType/condition
 * (mirrors dns_records.record_type's immutability elsewhere in this repo),
 * so this whole block is hidden once editing.
 */
function SourceFields({
  environmentId,
  fields,
  setField,
}: {
  environmentId: string;
  fields: AlertRuleFormFields;
  setField: <K extends keyof AlertRuleFormFields>(key: K, value: AlertRuleFormFields[K]) => void;
}) {
  const t = useTranslations("alerting");
  return (
    <>
      <div className="space-y-1.5">
        <Label htmlFor="alert-rule-source">{t("fields.source")}</Label>
        <select
          id="alert-rule-source"
          value={fields.source}
          onChange={(event) => setField("source", event.target.value as AlertRuleSource)}
          className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
        >
          {Object.values(ALERT_RULE_SOURCE).map((value) => (
            <option key={value} value={value}>
              {t(`sources.${value}`)}
            </option>
          ))}
        </select>
      </div>

      {fields.source === ALERT_RULE_SOURCE.CLOUDFLARE_NATIVE ? (
        <CloudflareNativeFields
          environmentId={environmentId}
          cfAlertType={fields.cfAlertType}
          onChange={(value) => setField("cfAlertType", value)}
        />
      ) : (
        <LokiQueryFields
          endpointUrl={fields.endpointUrl}
          onEndpointUrlChange={(value) => setField("endpointUrl", value)}
          query={fields.query}
          onQueryChange={(value) => setField("query", value)}
          forDuration={fields.forDuration}
          onForDurationChange={(value) => setField("forDuration", value)}
        />
      )}
    </>
  );
}

export function AlertRuleFormDialog({ environmentId, projectId, alertRule, onClose }: AlertRuleFormDialogProps) {
  const t = useTranslations("alerting");
  const getErrorMessage = useApiErrorMessage("alerting");
  const isEditing = Boolean(alertRule);
  const { fields, setField } = useAlertRuleFormFields(alertRule);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const create = useCreateAlertRule(environmentId);
  const update = useUpdateAlertRule(environmentId);
  const isSaving = create.isPending || update.isPending;

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    setErrorMessage(null);
    const callbacks = {
      onSuccess: () => onClose(),
      onError: (err: unknown) => setErrorMessage(getErrorMessage(err)),
    };
    if (isEditing && alertRule) {
      const { name, severity, channelIds } = fields;
      update.mutate({ id: alertRule.id, data: { name, severity, channelIds } }, callbacks);
      return;
    }
    create.mutate(buildCreatePayload(fields), callbacks);
  };

  return (
    <Dialog
      icon={IconNotification}
      title={isEditing ? t("form.editTitle") : t("form.createTitle")}
      onClose={onClose}
      closeLabel={t("form.cancel")}
    >
      <form onSubmit={handleSubmit} className="space-y-4 overflow-y-auto p-6">
        {errorMessage && <DialogErrorAlert message={errorMessage} />}

        <div className="space-y-1.5">
          <Label htmlFor="alert-rule-name">{t("fields.name")}</Label>
          <Input
            id="alert-rule-name"
            value={fields.name}
            onChange={(event) => setField("name", event.target.value)}
            required
          />
        </div>

        {!isEditing && <SourceFields environmentId={environmentId} fields={fields} setField={setField} />}

        <div className="space-y-1.5">
          <Label htmlFor="alert-rule-severity">{t("fields.severity")}</Label>
          <select
            id="alert-rule-severity"
            value={fields.severity}
            onChange={(event) => setField("severity", event.target.value)}
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          >
            {Object.values(ALERT_SEVERITY).map((value) => (
              <option key={value} value={value}>
                {t(`severities.${value}`)}
              </option>
            ))}
          </select>
        </div>

        <ChannelMultiselect
          projectId={projectId}
          selectedIds={fields.channelIds}
          onChange={(ids) => setField("channelIds", ids)}
        />

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
    </Dialog>
  );
}
