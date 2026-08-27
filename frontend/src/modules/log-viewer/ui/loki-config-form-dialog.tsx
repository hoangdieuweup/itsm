"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Eye, EyeOff, Plus } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/input";
import { Label } from "@/shared/ui/label";
import { Dialog, DialogErrorAlert } from "@/shared/ui/dialog";
import { useApiErrorMessage } from "@/shared/lib/handle-api-error";
import { LOKI_AUTH_TYPE, type LokiAuthType, type LokiConfig } from "@/entities/loki-config";
import { useCreateLokiConfig, useUpdateLokiConfig } from "../hooks/use-loki-config";
import { IconGrafana } from "@/shared/ui/icons";

interface LokiConfigFormDialogProps {
  environmentId: string;
  config: LokiConfig | null;
  onClose: () => void;
}

function submitLabel(t: ReturnType<typeof useTranslations>, isSaving: boolean, isEditing: boolean): string {
  if (isSaving) return t("form.saving");
  return isEditing ? t("form.save") : t("form.create");
}

function credentialHint(t: ReturnType<typeof useTranslations>, authType: LokiAuthType, isEditing: boolean): string {
  if (authType === LOKI_AUTH_TYPE.BASIC) return t("config.credentialHintBasic");
  if (authType === LOKI_AUTH_TYPE.BEARER) {
    return isEditing ? t("config.credentialKeepHint") : t("config.credentialHintBearer");
  }
  return "";
}

/**
 * Resolves what to send for `credential` on submit:
 * - a typed value always wins
 * - creating with no value sends null (explicit "no credential")
 * - editing with no value sends undefined (omit — keep the existing one;
 *   the backend clears it on its own when authType becomes "none",
 *   regardless of what accompanies that update)
 */
function resolveCredentialForSubmit(
  credential: string,
  isEditing: boolean,
): string | null | undefined {
  if (credential) return credential;
  return isEditing ? undefined : null;
}

function CredentialField({
  credential,
  onChange,
  authType,
  isEditing,
}: {
  credential: string;
  onChange: (value: string) => void;
  authType: LokiAuthType;
  isEditing: boolean;
}) {
  const t = useTranslations("logViewer");
  const [visible, setVisible] = useState(false);

  return (
    <div className="space-y-1.5">
      <Label htmlFor="loki-credential">{t("config.credential")}</Label>
      <div className="relative">
        <Input
          id="loki-credential"
          type={visible ? "text" : "password"}
          value={credential}
          onChange={(event) => onChange(event.target.value)}
          aria-describedby="loki-credential-hint"
          className="pr-10"
        />
        <button
          type="button"
          onClick={() => setVisible((current) => !current)}
          aria-label={visible ? t("form.hideCredential") : t("form.showCredential")}
          className="absolute inset-y-0 right-0 flex items-center px-3 text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
        >
          {visible ? <EyeOff className="size-3.5" aria-hidden="true" /> : <Eye className="size-3.5" aria-hidden="true" />}
        </button>
      </div>
      <p id="loki-credential-hint" className="text-xs text-muted-foreground">
        {credentialHint(t, authType, isEditing)}
      </p>
    </div>
  );
}

export function LokiConfigFormDialog({ environmentId, config, onClose }: LokiConfigFormDialogProps) {
  const t = useTranslations("logViewer");
  const getErrorMessage = useApiErrorMessage("logViewer");
  const isEditing = Boolean(config);

  const [endpointUrl, setEndpointUrl] = useState(config?.endpointUrl ?? "");
  const [tenantId, setTenantId] = useState(config?.tenantId ?? "");
  const [authType, setAuthType] = useState<LokiAuthType>(config?.authType ?? LOKI_AUTH_TYPE.NONE);
  const [credential, setCredential] = useState("");
  const [defaultQuery, setDefaultQuery] = useState(config?.defaultQuery ?? "");
  const [defaultRangeMinutes, setDefaultRangeMinutes] = useState(config?.defaultRangeMinutes ?? 60);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const create = useCreateLokiConfig(environmentId);
  const update = useUpdateLokiConfig(environmentId);
  const isSaving = create.isPending || update.isPending;
  const needsCredential = authType !== LOKI_AUTH_TYPE.NONE;

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    setErrorMessage(null);
    const callbacks = {
      onSuccess: () => onClose(),
      onError: (err: unknown) => setErrorMessage(getErrorMessage(err)),
    };
    const base = { endpointUrl, tenantId: tenantId || null, authType, defaultQuery, defaultRangeMinutes };
    if (isEditing) {
      update.mutate({ ...base, credential: resolveCredentialForSubmit(credential, true) }, callbacks);
    } else {
      create.mutate({ ...base, credential: resolveCredentialForSubmit(credential, false) ?? null }, callbacks);
    }
  };

  return (
    <Dialog
      icon={IconGrafana}
      title={isEditing ? t("config.edit") : t("config.title")}
      onClose={onClose}
      closeLabel={t("form.cancel")}
    >
      <form onSubmit={handleSubmit} className="space-y-4 overflow-y-auto p-6">
        {errorMessage && <DialogErrorAlert message={errorMessage} />}

        <div className="space-y-1.5">
          <Label htmlFor="loki-endpoint-url">{t("config.endpointUrl")}</Label>
          <Input
            id="loki-endpoint-url"
            type="url"
            value={endpointUrl}
            onChange={(event) => setEndpointUrl(event.target.value)}
            required
          />
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="loki-tenant-id">{t("config.tenantId")}</Label>
          <Input
            id="loki-tenant-id"
            value={tenantId}
            onChange={(event) => setTenantId(event.target.value)}
            aria-describedby="loki-tenant-id-hint"
          />
          <p id="loki-tenant-id-hint" className="text-xs text-muted-foreground">
            {t("config.tenantIdHint")}
          </p>
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="loki-auth-type">{t("config.authType")}</Label>
          <select
            id="loki-auth-type"
            value={authType}
            onChange={(event) => setAuthType(event.target.value as LokiAuthType)}
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          >
            {Object.values(LOKI_AUTH_TYPE).map((type) => (
              <option key={type} value={type}>
                {t(`config.authType${type.charAt(0).toUpperCase()}${type.slice(1)}`)}
              </option>
            ))}
          </select>
        </div>

        {needsCredential && (
          <CredentialField
            credential={credential}
            onChange={setCredential}
            authType={authType}
            isEditing={isEditing}
          />
        )}

        <div className="space-y-1.5">
          <Label htmlFor="loki-default-query">{t("config.defaultQuery")}</Label>
          <Input
            id="loki-default-query"
            value={defaultQuery}
            onChange={(event) => setDefaultQuery(event.target.value)}
            className="font-mono"
          />
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="loki-default-range">{t("config.defaultRangeMinutes")}</Label>
          <Input
            id="loki-default-range"
            type="number"
            min={1}
            value={defaultRangeMinutes}
            onChange={(event) => setDefaultRangeMinutes(Number(event.target.value))}
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
    </Dialog>
  );
}
