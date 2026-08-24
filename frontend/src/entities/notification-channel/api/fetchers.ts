import { apiFetch } from "@/shared/lib/api-client";
import { API_CONFIG } from "@/shared/constants/api";
import { notificationChannelSchema, type NotificationChannel } from "../model/schema";

export async function fetchNotificationChannels(
  projectId: string,
  environmentId?: string,
): Promise<NotificationChannel[]> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.NOTIFICATION_CHANNELS.ROOT, {
    params: { projectId, ...(environmentId && { environmentId }) },
  });
  return notificationChannelSchema.array().parse(raw);
}
