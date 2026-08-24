import { apiFetch } from "@/shared/lib/api-client";
import { API_CONFIG } from "@/shared/constants/api";
import {
  notificationChannelSchema,
  type NotificationChannel,
  type NotificationChannelType,
} from "@/entities/notification-channel";

export interface NotificationChannelFormValues {
  projectId: string;
  environmentId: string | null;
  type: NotificationChannelType;
  name: string;
  config: Record<string, unknown>;
}

export async function createNotificationChannel(data: NotificationChannelFormValues): Promise<NotificationChannel> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.NOTIFICATION_CHANNELS.ROOT, { method: "POST", data });
  return notificationChannelSchema.parse(raw);
}

export async function updateNotificationChannel(
  id: string,
  data: Partial<Pick<NotificationChannelFormValues, "name" | "config">> & { isActive?: boolean },
): Promise<NotificationChannel> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.NOTIFICATION_CHANNELS.DETAIL(id), {
    method: "PATCH",
    data,
  });
  return notificationChannelSchema.parse(raw);
}

export async function deleteNotificationChannel(id: string): Promise<void> {
  await apiFetch<unknown>(API_CONFIG.ENDPOINTS.NOTIFICATION_CHANNELS.DETAIL(id), { method: "DELETE" });
}

export async function testSendNotificationChannel(id: string, message?: string): Promise<void> {
  await apiFetch<unknown>(API_CONFIG.ENDPOINTS.NOTIFICATION_CHANNELS.TEST_SEND(id), {
    method: "POST",
    data: { message },
  });
}
