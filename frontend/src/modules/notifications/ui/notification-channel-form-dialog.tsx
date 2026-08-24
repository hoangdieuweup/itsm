"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Bell, Eye, EyeOff, Plus } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { Input } from "@/shared/ui/input";
import { Label } from "@/shared/ui/label";
import { Dialog, DialogErrorAlert } from "@/shared/ui/dialog";
import { useApiErrorMessage } from "@/shared/lib/handle-api-error";
import {
  NOTIFICATION_CHANNEL_TYPE,
  type NotificationChannel,
  type NotificationChannelType,
} from "@/entities/notification-channel";
import { useCreateNotificationChannel } from "../hooks/use-create-channel";
import { useUpdateNotificationChannel } from "../hooks/use-update-channel";

interface NotificationChannelFormDialogProps {
  projectId: string;
  environmentId: string | null;
  channel: NotificationChannel | null;
  onClose: () => void;
}

function submitLabel(t: ReturnType<typeof useTranslations>, isSaving: boolean, isEditing: boolean): string {
  if (isSaving) return t("form.saving");
  return isEditing ? t("form.save") : t("form.create");
}

function SecretField({
  id,
  label,
  value,
  onChange,
  hint,
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  hint?: string;
}) {
  const t = useTranslations("notifications");
  const [visible, setVisible] = useState(false);
  const hintId = `${id}-hint`;

  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      <div className="relative">
        <Input
          id={id}
          type={visible ? "text" : "password"}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          aria-describedby={hint ? hintId : undefined}
          className="pr-10"
        />
        <button
          type="button"
          onClick={() => setVisible((current) => !current)}
          aria-label={visible ? t("form.hideSecret") : t("form.showSecret")}
          className="absolute inset-y-0 right-0 flex items-center px-3 text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
        >
          {visible ? <EyeOff className="size-3.5" aria-hidden="true" /> : <Eye className="size-3.5" aria-hidden="true" />}
        </button>
      </div>
      {hint && (
        <p id={hintId} className="text-xs text-muted-foreground">
          {hint}
        </p>
      )}
    </div>
  );
}

function EmailFields({ recipients, onChange }: { recipients: string; onChange: (value: string) => void }) {
  const t = useTranslations("notifications");
  return (
    <div className="space-y-1.5">
      <Label htmlFor="channel-recipients">{t("fields.recipients")}</Label>
      <Input
        id="channel-recipients"
        value={recipients}
        onChange={(event) => onChange(event.target.value)}
        aria-describedby="channel-recipients-hint"
        required
      />
      <p id="channel-recipients-hint" className="text-xs text-muted-foreground">
        {t("fields.recipientsHint")}
      </p>
    </div>
  );
}

function TelegramFields({
  botToken,
  onBotTokenChange,
  chatId,
  onChatIdChange,
  isEditing,
}: {
  botToken: string;
  onBotTokenChange: (value: string) => void;
  chatId: string;
  onChatIdChange: (value: string) => void;
  isEditing: boolean;
}) {
  const t = useTranslations("notifications");
  return (
    <>
      <SecretField
        id="channel-bot-token"
        label={t("fields.botToken")}
        value={botToken}
        onChange={onBotTokenChange}
        hint={isEditing ? t("fields.secretKeepHint") : undefined}
      />
      <div className="space-y-1.5">
        <Label htmlFor="channel-chat-id">{t("fields.chatId")}</Label>
        <Input id="channel-chat-id" value={chatId} onChange={(event) => onChatIdChange(event.target.value)} required />
      </div>
    </>
  );
}

function BaseVnFields({
  webhookUrl,
  onWebhookUrlChange,
  botName,
  onBotNameChange,
  messageTemplate,
  onMessageTemplateChange,
  isEditing,
}: {
  webhookUrl: string;
  onWebhookUrlChange: (value: string) => void;
  botName: string;
  onBotNameChange: (value: string) => void;
  messageTemplate: string;
  onMessageTemplateChange: (value: string) => void;
  isEditing: boolean;
}) {
  const t = useTranslations("notifications");
  return (
    <>
      <SecretField
        id="channel-webhook-url"
        label={t("fields.webhookUrl")}
        value={webhookUrl}
        onChange={onWebhookUrlChange}
        hint={isEditing ? t("fields.secretKeepHint") : undefined}
      />
      <div className="space-y-1.5">
        <Label htmlFor="channel-bot-name">{t("fields.botName")}</Label>
        <Input id="channel-bot-name" value={botName} onChange={(event) => onBotNameChange(event.target.value)} />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="channel-message-template">{t("fields.messageTemplate")}</Label>
        <Input
          id="channel-message-template"
          value={messageTemplate}
          onChange={(event) => onMessageTemplateChange(event.target.value)}
          aria-describedby="channel-message-template-hint"
        />
        <p id="channel-message-template-hint" className="text-xs text-muted-foreground">
          {t("fields.messageTemplateHint")}
        </p>
      </div>
    </>
  );
}

function OtherFields({ json, onChange }: { json: string; onChange: (value: string) => void }) {
  const t = useTranslations("notifications");
  return (
    <div className="space-y-1.5">
      <Label htmlFor="channel-other-config">{t("fields.otherConfig")}</Label>
      <textarea
        id="channel-other-config"
        value={json}
        onChange={(event) => onChange(event.target.value)}
        rows={4}
        className="w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
      />
    </div>
  );
}

function computeInitialFields(channel: NotificationChannel | null, type: NotificationChannelType) {
  return {
    recipients: Array.isArray(channel?.config.recipients) ? (channel.config.recipients as string[]).join(", ") : "",
    chatId: typeof channel?.config.chat_id === "string" ? channel.config.chat_id : "",
    botName: typeof channel?.config.bot_name === "string" ? channel.config.bot_name : "",
    messageTemplate: typeof channel?.config.message_template === "string" ? channel.config.message_template : "",
    otherJson: channel && type === NOTIFICATION_CHANNEL_TYPE.OTHER ? JSON.stringify(channel.config) : "",
  };
}

function ChannelTypeFields({
  type,
  isEditing,
  recipients,
  onRecipientsChange,
  botToken,
  onBotTokenChange,
  chatId,
  onChatIdChange,
  webhookUrl,
  onWebhookUrlChange,
  botName,
  onBotNameChange,
  messageTemplate,
  onMessageTemplateChange,
  otherJson,
  onOtherJsonChange,
}: {
  type: NotificationChannelType;
  isEditing: boolean;
  recipients: string;
  onRecipientsChange: (value: string) => void;
  botToken: string;
  onBotTokenChange: (value: string) => void;
  chatId: string;
  onChatIdChange: (value: string) => void;
  webhookUrl: string;
  onWebhookUrlChange: (value: string) => void;
  botName: string;
  onBotNameChange: (value: string) => void;
  messageTemplate: string;
  onMessageTemplateChange: (value: string) => void;
  otherJson: string;
  onOtherJsonChange: (value: string) => void;
}) {
  if (type === NOTIFICATION_CHANNEL_TYPE.EMAIL) {
    return <EmailFields recipients={recipients} onChange={onRecipientsChange} />;
  }
  if (type === NOTIFICATION_CHANNEL_TYPE.TELEGRAM) {
    return (
      <TelegramFields
        botToken={botToken}
        onBotTokenChange={onBotTokenChange}
        chatId={chatId}
        onChatIdChange={onChatIdChange}
        isEditing={isEditing}
      />
    );
  }
  if (type === NOTIFICATION_CHANNEL_TYPE.BASE_VN) {
    return (
      <BaseVnFields
        webhookUrl={webhookUrl}
        onWebhookUrlChange={onWebhookUrlChange}
        botName={botName}
        onBotNameChange={onBotNameChange}
        messageTemplate={messageTemplate}
        onMessageTemplateChange={onMessageTemplateChange}
        isEditing={isEditing}
      />
    );
  }
  return <OtherFields json={otherJson} onChange={onOtherJsonChange} />;
}

function buildConfig(
  type: NotificationChannelType,
  fields: {
    recipients: string;
    botToken: string;
    chatId: string;
    webhookUrl: string;
    botName: string;
    messageTemplate: string;
    otherJson: string;
  },
  isEditing: boolean,
): { config: Record<string, unknown>; error: string | null } {
  if (type === NOTIFICATION_CHANNEL_TYPE.EMAIL) {
    const recipients = fields.recipients
      .split(",")
      .map((r) => r.trim())
      .filter(Boolean);
    return { config: { recipients }, error: null };
  }
  if (type === NOTIFICATION_CHANNEL_TYPE.TELEGRAM) {
    const config: Record<string, unknown> = { chat_id: fields.chatId };
    if (fields.botToken) config.bot_token = fields.botToken;
    else if (!isEditing) return { config: {}, error: "botTokenRequired" };
    return { config, error: null };
  }
  if (type === NOTIFICATION_CHANNEL_TYPE.BASE_VN) {
    const config: Record<string, unknown> = { bot_name: fields.botName, message_template: fields.messageTemplate };
    if (fields.webhookUrl) config.webhook_url = fields.webhookUrl;
    else if (!isEditing) return { config: {}, error: "webhookUrlRequired" };
    return { config, error: null };
  }
  try {
    return { config: fields.otherJson ? JSON.parse(fields.otherJson) : {}, error: null };
  } catch {
    return { config: {}, error: "invalidJson" };
  }
}

export function NotificationChannelFormDialog({
  projectId,
  environmentId,
  channel,
  onClose,
}: NotificationChannelFormDialogProps) {
  const t = useTranslations("notifications");
  const getErrorMessage = useApiErrorMessage("notifications");
  const isEditing = Boolean(channel);

  const [type, setType] = useState<NotificationChannelType>(channel?.type ?? NOTIFICATION_CHANNEL_TYPE.EMAIL);
  const [name, setName] = useState(channel?.name ?? "");
  const initialFields = computeInitialFields(channel, type);
  const [recipients, setRecipients] = useState(initialFields.recipients);
  const [botToken, setBotToken] = useState("");
  const [chatId, setChatId] = useState(initialFields.chatId);
  const [webhookUrl, setWebhookUrl] = useState("");
  const [botName, setBotName] = useState(initialFields.botName);
  const [messageTemplate, setMessageTemplate] = useState(initialFields.messageTemplate);
  const [otherJson, setOtherJson] = useState(initialFields.otherJson);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const create = useCreateNotificationChannel(projectId);
  const update = useUpdateNotificationChannel(projectId);
  const isSaving = create.isPending || update.isPending;

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    setErrorMessage(null);
    const built = buildConfig(
      type,
      { recipients, botToken, chatId, webhookUrl, botName, messageTemplate, otherJson },
      isEditing,
    );
    if (built.error) {
      setErrorMessage(t(`form.errors.${built.error}`));
      return;
    }
    const callbacks = {
      onSuccess: () => onClose(),
      onError: (err: unknown) => setErrorMessage(getErrorMessage(err)),
    };
    if (isEditing && channel) {
      update.mutate({ id: channel.id, data: { name, config: built.config } }, callbacks);
    } else {
      create.mutate({ projectId, environmentId, type, name, config: built.config }, callbacks);
    }
  };

  return (
    <Dialog
      icon={Bell}
      title={isEditing ? t("form.editTitle") : t("form.createTitle")}
      onClose={onClose}
      closeLabel={t("form.cancel")}
    >
      <form onSubmit={handleSubmit} className="space-y-4 overflow-y-auto p-6">
        {errorMessage && <DialogErrorAlert message={errorMessage} />}

        <div className="space-y-1.5">
          <Label htmlFor="channel-name">{t("fields.name")}</Label>
          <Input id="channel-name" value={name} onChange={(event) => setName(event.target.value)} required />
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="channel-type">{t("fields.type")}</Label>
          <select
            id="channel-type"
            value={type}
            onChange={(event) => setType(event.target.value as NotificationChannelType)}
            disabled={isEditing}
            aria-describedby={isEditing ? "channel-type-hint" : undefined}
            className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          >
            {Object.values(NOTIFICATION_CHANNEL_TYPE).map((channelType) => (
              <option key={channelType} value={channelType}>
                {t(`types.${channelType}`)}
              </option>
            ))}
          </select>
          {isEditing && (
            <p id="channel-type-hint" className="text-xs text-muted-foreground">
              {t("fields.typeImmutableHint")}
            </p>
          )}
        </div>

        <ChannelTypeFields
          type={type}
          isEditing={isEditing}
          recipients={recipients}
          onRecipientsChange={setRecipients}
          botToken={botToken}
          onBotTokenChange={setBotToken}
          chatId={chatId}
          onChatIdChange={setChatId}
          webhookUrl={webhookUrl}
          onWebhookUrlChange={setWebhookUrl}
          botName={botName}
          onBotNameChange={setBotName}
          messageTemplate={messageTemplate}
          onMessageTemplateChange={setMessageTemplate}
          otherJson={otherJson}
          onOtherJsonChange={setOtherJson}
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
