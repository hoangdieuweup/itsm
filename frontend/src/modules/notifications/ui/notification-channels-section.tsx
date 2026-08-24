"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Bell, Plus, Pencil, Trash2, Send, CheckCircle2, XCircle } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { ConfirmDialog } from "@/shared/ui/confirm-dialog";
import { Can } from "@/entities/permission";
import { ACTIONS, RESOURCES } from "@/shared/constants/permissions";
import { useNotificationChannelsQuery, type NotificationChannel } from "@/entities/notification-channel";
import { useApiErrorMessage } from "@/shared/lib/handle-api-error";
import { useDeleteNotificationChannel } from "../hooks/use-delete-channel";
import { useTestSendNotificationChannel } from "../hooks/use-test-send-channel";
import { NotificationChannelFormDialog } from "./notification-channel-form-dialog";

function TestSendButton({ channelId }: { channelId: string }) {
  const t = useTranslations("notifications");
  const getErrorMessage = useApiErrorMessage("notifications");
  const testSend = useTestSendNotificationChannel();

  return (
    <div className="flex items-center gap-2">
      <button
        type="button"
        onClick={() => testSend.mutate({ id: channelId })}
        disabled={testSend.isPending}
        aria-label={t("actions.sendTest")}
        className="cursor-pointer text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary disabled:cursor-not-allowed disabled:opacity-50"
      >
        <Send className="size-3.5" aria-hidden="true" />
      </button>
      {testSend.isSuccess && (
        <span
          role="status"
          aria-atomic="true"
          className="flex items-center gap-1 text-xs text-emerald-600 dark:text-emerald-400"
        >
          <CheckCircle2 className="size-3.5" aria-hidden="true" /> {t("actions.testSendSuccess")}
        </span>
      )}
      {testSend.isError && (
        <span role="alert" className="flex items-center gap-1 text-xs text-destructive">
          <XCircle className="size-3.5" aria-hidden="true" /> {getErrorMessage(testSend.error)}
        </span>
      )}
    </div>
  );
}

export function NotificationChannelsSection({ projectId }: { projectId: string }) {
  const t = useTranslations("notifications");
  const { data: channels } = useNotificationChannelsQuery(projectId);
  const deleteChannel = useDeleteNotificationChannel(projectId);

  const [formTarget, setFormTarget] = useState<NotificationChannel | "create" | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<NotificationChannel | null>(null);

  return (
    <section className="flex flex-col gap-3 rounded-xl border bg-card p-5">
      <div className="flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-sm font-bold text-foreground">
          <Bell className="size-4" aria-hidden="true" /> {t("section.title")}
        </h2>
        <Can I={ACTIONS.CREATE} a={RESOURCES.NOTIFICATION_CHANNEL}>
          <Button size="sm" onClick={() => setFormTarget("create")}>
            <Plus className="mr-1.5 size-3.5" aria-hidden="true" /> {t("actions.add")}
          </Button>
        </Can>
      </div>

      {channels.length === 0 && <p className="text-sm text-muted-foreground">{t("section.empty")}</p>}

      <div className="flex flex-col divide-y">
        {channels.map((channel) => (
          <div key={channel.id} className="flex items-center justify-between py-2 text-sm">
            <div className="flex items-center gap-2">
              <span className="font-medium text-foreground">{channel.name}</span>
              <span className="rounded-full bg-muted px-2 py-0.5 text-[10px] font-bold uppercase text-muted-foreground">
                {t(`types.${channel.type}`)}
              </span>
              {!channel.isActive && (
                <span className="rounded-full bg-amber-50 px-2 py-0.5 text-[10px] font-bold uppercase text-amber-700 dark:bg-amber-950/60 dark:text-amber-300">
                  {t("section.inactive")}
                </span>
              )}
            </div>
            <div className="flex items-center gap-3">
              <Can I={ACTIONS.UPDATE} a={RESOURCES.NOTIFICATION_CHANNEL}>
                <TestSendButton channelId={channel.id} />
              </Can>
              <Can I={ACTIONS.UPDATE} a={RESOURCES.NOTIFICATION_CHANNEL}>
                <button
                  type="button"
                  onClick={() => setFormTarget(channel)}
                  aria-label={t("actions.edit")}
                  className="cursor-pointer text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                >
                  <Pencil className="size-3.5" aria-hidden="true" />
                </button>
              </Can>
              <Can I={ACTIONS.DELETE} a={RESOURCES.NOTIFICATION_CHANNEL}>
                <button
                  type="button"
                  onClick={() => setDeleteTarget(channel)}
                  aria-label={t("actions.delete")}
                  className="cursor-pointer text-muted-foreground hover:text-destructive focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                >
                  <Trash2 className="size-3.5" aria-hidden="true" />
                </button>
              </Can>
            </div>
          </div>
        ))}
      </div>

      {formTarget !== null && (
        <NotificationChannelFormDialog
          projectId={projectId}
          environmentId={null}
          channel={formTarget === "create" ? null : formTarget}
          onClose={() => setFormTarget(null)}
        />
      )}

      <ConfirmDialog
        isOpen={deleteTarget !== null}
        onClose={() => setDeleteTarget(null)}
        onConfirm={() => {
          if (deleteTarget) {
            deleteChannel.mutate(deleteTarget.id, { onSuccess: () => setDeleteTarget(null) });
          }
        }}
        title={t("section.deleteConfirm.title")}
        description={t("section.deleteConfirm.description", { name: deleteTarget?.name ?? "" })}
        variant="destructive"
        isLoading={deleteChannel.isPending}
      />
    </section>
  );
}
