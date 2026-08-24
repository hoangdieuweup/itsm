"use client";

import { Suspense } from "react";
import { useTranslations } from "next-intl";
import { useNotificationChannelsQuery } from "@/entities/notification-channel";

interface ChannelMultiselectProps {
  projectId: string;
  selectedIds: string[];
  onChange: (ids: string[]) => void;
}

function ChannelMultiselectList({ projectId, selectedIds, onChange }: ChannelMultiselectProps) {
  const t = useTranslations("alerting");
  const { data: channels } = useNotificationChannelsQuery(projectId);

  function toggle(id: string) {
    onChange(selectedIds.includes(id) ? selectedIds.filter((x) => x !== id) : [...selectedIds, id]);
  }

  if (channels.length === 0) {
    return <p className="text-sm text-muted-foreground">{t("fields.noChannels")}</p>;
  }

  return (
    <>
      {channels.map((channel) => (
        <label key={channel.id} className="flex min-w-0 items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={selectedIds.includes(channel.id)}
            onChange={() => toggle(channel.id)}
            className="size-4 shrink-0 rounded border-input focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
          />
          <span className="truncate">{channel.name}</span>
          <span className="shrink-0 text-xs text-muted-foreground">({channel.type})</span>
        </label>
      ))}
    </>
  );
}

/**
 * useNotificationChannelsQuery is a suspense query — safe for a page body
 * (which already sits under a route-level Suspense boundary) but not for a
 * modal opened after the page has settled: without its own boundary here,
 * the suspend would bubble up and unmount the whole page behind the dialog
 * while channels load. Scoping Suspense to just the list keeps the dialog
 * shell and its other fields mounted throughout.
 */
export function ChannelMultiselect({ projectId, selectedIds, onChange }: ChannelMultiselectProps) {
  const t = useTranslations("alerting");

  return (
    <fieldset className="space-y-1.5">
      <legend className="text-sm font-medium text-foreground">{t("fields.channels")}</legend>
      <div className="flex flex-col gap-2 rounded-md border border-input p-3">
        <Suspense fallback={<div className="h-5 w-32 animate-pulse rounded bg-muted" />}>
          <ChannelMultiselectList projectId={projectId} selectedIds={selectedIds} onChange={onChange} />
        </Suspense>
      </div>
    </fieldset>
  );
}
