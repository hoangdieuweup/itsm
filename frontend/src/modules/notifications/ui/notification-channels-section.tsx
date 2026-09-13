"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { Bell, Plus, Pencil, Trash2, Send, CheckCircle2, XCircle } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { Skeleton } from "@/shared/ui/skeleton";
import { ConfirmDialog } from "@/shared/ui/confirm-dialog";
import { CanInProject } from "@/entities/permission";
import { ACTIONS, RESOURCES } from "@/shared/constants/permissions";
import { useNotificationChannelsQuery, type NotificationChannel } from "@/entities/notification-channel";
import { useApiErrorMessage } from "@/shared/lib/handle-api-error";
import { useDeleteNotificationChannel } from "../hooks/use-delete-channel";
import { useTestSendNotificationChannel } from "../hooks/use-test-send-channel";
import { NotificationChannelFormDialog } from "./notification-channel-form-dialog";
import { IconNotification } from "@/shared/ui/icons";

import { m } from "@/shared/lib/motion";

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
        className="flex size-7 items-center justify-center rounded-lg border border-border/60 bg-muted/40 text-muted-foreground transition-all hover:border-primary/40 hover:bg-primary/10 hover:text-primary disabled:cursor-not-allowed disabled:opacity-50 cursor-pointer shadow-2xs"
        title={t("actions.sendTest")}
      >
        <Send className="size-3.5" aria-hidden="true" />
      </button>
      {testSend.isSuccess && (
        <span
          role="status"
          aria-atomic="true"
          className="flex items-center gap-1 font-mono text-xs text-emerald-600 dark:text-emerald-400 font-semibold"
        >
          <CheckCircle2 className="size-3.5" aria-hidden="true" /> {t("actions.testSendSuccess")}
        </span>
      )}
      {testSend.isError && (
        <span role="alert" className="flex items-center gap-1 font-mono text-xs text-destructive">
          <XCircle className="size-3.5" aria-hidden="true" /> {getErrorMessage(testSend.error)}
        </span>
      )}
    </div>
  );
}

export function NotificationChannelsSection({ projectId }: { projectId: string }) {
  const t = useTranslations("notifications");
  const { data: channels = [], isLoading } = useNotificationChannelsQuery(projectId);
  const deleteChannel = useDeleteNotificationChannel(projectId);

  const [formTarget, setFormTarget] = useState<NotificationChannel | "create" | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<NotificationChannel | null>(null);

  return (
    <CanInProject I={ACTIONS.READ} a={RESOURCES.PROJECT_NOTIFICATION_CHANNEL}>
    <m.section
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay: 0.15 }}
      className="mt-6 flex flex-col gap-5 rounded-3xl border border-border/50 bg-card/75 p-6 backdrop-blur-xl shadow-lg shadow-black/5 dark:shadow-black/20"
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <IconNotification className="size-8 shrink-0 rounded-xl shadow-xs" />
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-bold uppercase tracking-wider text-foreground">
                {t("section.title")}
              </h2>
              <span className="inline-flex items-center rounded-full border border-amber-500/30 bg-amber-500/15 px-2 py-0.5 font-mono text-[11px] font-bold text-amber-600 dark:text-amber-400">
                {channels.length}
              </span>
            </div>
          </div>
        </div>

        <CanInProject I={ACTIONS.CREATE} a={RESOURCES.PROJECT_NOTIFICATION_CHANNEL}>
          <Button
            size="sm"
            onClick={() => setFormTarget("create")}
            className="gap-1.5 bg-gradient-to-r from-amber-600 to-orange-600 font-semibold text-white shadow-xs hover:from-amber-700 hover:to-orange-700"
          >
            <Plus className="size-3.5" aria-hidden="true" /> {t("actions.add")}
          </Button>
        </CanInProject>
      </div>

      {isLoading ? (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Skeleton className="h-20 w-full rounded-3xl" />
          <Skeleton className="h-20 w-full rounded-3xl" />
        </div>
      ) : channels.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-border/60 bg-muted/20 py-10 text-center">
          <div className="flex size-10 items-center justify-center rounded-xl bg-muted/60 text-muted-foreground mb-2">
            <Bell className="size-5" aria-hidden="true" />
          </div>
          <p className="text-sm font-medium text-muted-foreground">{t("section.empty")}</p>
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {channels.map((channel) => (
            <div
              key={channel.id}
              className="flex items-center justify-between gap-4 rounded-2xl border border-border/60 bg-card/80 px-5 py-3.5 backdrop-blur-md transition-all hover:border-amber-500/40 hover:shadow-md shadow-2xs"
            >
              {/* Left: avatar + info */}
              <div className="flex items-center gap-3 min-w-0">
                <div className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-muted/60 text-foreground font-bold font-mono text-xs">
                  {channel.type.slice(0, 2).toUpperCase()}
                </div>
                <div className="flex items-center gap-2 min-w-0 flex-wrap">
                  <span className="font-bold text-sm text-foreground truncate">{channel.name}</span>
                  <span className="rounded-md bg-muted px-1.5 py-0.5 text-[9px] font-bold uppercase text-muted-foreground shrink-0">
                    {t(`types.${channel.type}`)}
                  </span>
                  <span
                    className={`inline-flex items-center gap-1 text-[11px] font-medium shrink-0 ${
                      channel.isActive
                        ? "text-emerald-600 dark:text-emerald-400"
                        : "text-amber-600 dark:text-amber-400"
                    }`}
                  >
                    <span
                      className={`size-1.5 rounded-full ${
                        channel.isActive ? "bg-emerald-500" : "bg-amber-500"
                      }`}
                    />
                    {channel.isActive ? "Active" : t("section.inactive")}
                  </span>
                </div>
              </div>

              {/* Right: actions */}
              <div className="flex items-center gap-1 shrink-0">
                <CanInProject I={ACTIONS.UPDATE} a={RESOURCES.PROJECT_NOTIFICATION_CHANNEL}>
                  <TestSendButton channelId={channel.id} />
                </CanInProject>
                <CanInProject I={ACTIONS.UPDATE} a={RESOURCES.PROJECT_NOTIFICATION_CHANNEL}>
                  <button
                    type="button"
                    onClick={() => setFormTarget(channel)}
                    aria-label={t("actions.edit")}
                    className="flex size-7 items-center justify-center rounded-lg text-muted-foreground hover:bg-muted hover:text-foreground cursor-pointer"
                    title={t("actions.edit")}
                  >
                    <Pencil className="size-3.5" aria-hidden="true" />
                  </button>
                </CanInProject>
                <CanInProject I={ACTIONS.DELETE} a={RESOURCES.PROJECT_NOTIFICATION_CHANNEL}>
                  <button
                    type="button"
                    onClick={() => setDeleteTarget(channel)}
                    aria-label={t("actions.delete")}
                    className="flex size-7 items-center justify-center rounded-lg text-rose-600 hover:bg-rose-500/10 hover:text-rose-700 dark:hover:bg-rose-950/50 cursor-pointer"
                    title={t("actions.delete")}
                  >
                    <Trash2 className="size-3.5" aria-hidden="true" />
                  </button>
                </CanInProject>
              </div>
            </div>
          ))}
        </div>
      )}

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
    </m.section>
    </CanInProject>
  );
}
