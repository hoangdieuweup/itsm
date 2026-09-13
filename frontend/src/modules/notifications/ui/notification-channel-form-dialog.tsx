"use client";

import { Suspense, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { Eye, EyeOff, Plus, Search } from "lucide-react";
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
import { useUsers, USER_STATUS } from "@/entities/user";
import { PAGINATION } from "@/shared/constants/pagination";
import { IconGmail, IconTelegram, IconNotification } from "@/shared/ui/icons";
import { useCreateNotificationChannel } from "../hooks/use-create-channel";
import { useUpdateNotificationChannel } from "../hooks/use-update-channel";

function getChannelIcon(channelType: NotificationChannelType) {
  if (channelType === NOTIFICATION_CHANNEL_TYPE.EMAIL) return IconGmail;
  if (channelType === NOTIFICATION_CHANNEL_TYPE.TELEGRAM) return IconTelegram;
  return IconNotification;
}

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

function EmailRecipientsPickerList({
  selectedEmails,
  onChange,
}: {
  selectedEmails: string[];
  onChange: (emails: string[]) => void;
}) {
  const t = useTranslations("notifications");
  const { data } = useUsers(PAGINATION.MAX_PAGE_SIZE, 0);
  const [search, setSearch] = useState("");

  const activeUsers = useMemo(
    () => data.items.filter((u) => u.status === USER_STATUS.ACTIVE),
    [data.items],
  );

  const filtered = useMemo(() => {
    if (!search.trim()) return activeUsers;
    const q = search.toLowerCase();
    return activeUsers.filter(
      (u) => u.name.toLowerCase().includes(q) || u.email.toLowerCase().includes(q),
    );
  }, [activeUsers, search]);

  function toggle(email: string) {
    onChange(
      selectedEmails.includes(email)
        ? selectedEmails.filter((e) => e !== email)
        : [...selectedEmails, email],
    );
  }

  return (
    <>
      <div className="relative">
        <Search className="pointer-events-none absolute left-2 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
        <input
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          placeholder={t("fields.recipientsSearch")}
          className="h-7 w-full rounded-md border border-input bg-transparent pl-7 pr-2 text-sm outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-1 focus-visible:ring-ring/50"
          aria-label={t("fields.recipientsSearch")}
        />
      </div>

      <div className="flex max-h-40 flex-col overflow-y-auto">
        {filtered.length === 0 && (
          <p className="py-2 text-center text-xs text-muted-foreground">{t("fields.recipientsEmpty")}</p>
        )}
        {filtered.map((user) => (
          <label
            key={user.id}
            className="flex min-w-0 cursor-pointer items-center gap-2 rounded px-1.5 py-1 text-sm transition-colors hover:bg-accent"
          >
            <input
              type="checkbox"
              checked={selectedEmails.includes(user.email)}
              onChange={() => toggle(user.email)}
              className="size-3.5 shrink-0 rounded border-input accent-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
            />
            <span className="truncate">{user.name}</span>
            <span className="ml-auto shrink-0 text-xs text-muted-foreground">{user.email}</span>
          </label>
        ))}
      </div>
    </>
  );
}

/**
 * useUsers is a suspense query — needs its own Suspense boundary inside the
 * dialog to avoid suspending the entire page when the dialog opens.
 * Same pattern as ChannelMultiselect in modules/alerting.
 */
function EmailFields({
  selectedEmails,
  onChange,
}: {
  selectedEmails: string[];
  onChange: (emails: string[]) => void;
}) {
  const t = useTranslations("notifications");
  return (
    <fieldset className="space-y-1.5">
      <legend className="text-sm font-medium text-foreground">{t("fields.recipients")}</legend>
      <p className="text-xs text-muted-foreground">{t("fields.recipientsHint")}</p>
      <div className="flex flex-col gap-1.5 rounded-md border border-input p-2">
        <Suspense fallback={<div className="h-5 w-32 animate-pulse rounded bg-muted" />}>
          <EmailRecipientsPickerList selectedEmails={selectedEmails} onChange={onChange} />
        </Suspense>
      </div>
    </fieldset>
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
    recipients: Array.isArray(channel?.config.recipients) ? (channel.config.recipients as string[]) : [],
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
  recipients: string[];
  onRecipientsChange: (emails: string[]) => void;
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
    return <EmailFields selectedEmails={recipients} onChange={onRecipientsChange} />;
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
    recipients: string[];
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
    return { config: { recipients: fields.recipients }, error: null };
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
  const [recipients, setRecipients] = useState<string[]>(initialFields.recipients);
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
      icon={getChannelIcon(type)}
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
