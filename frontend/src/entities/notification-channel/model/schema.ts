import { z } from "zod";

export const NOTIFICATION_CHANNEL_TYPES = ["email", "base_vn", "telegram", "other"] as const;
export type NotificationChannelType = (typeof NOTIFICATION_CHANNEL_TYPES)[number];

export const notificationChannelSchema = z.object({
  id: z.uuid(),
  projectId: z.uuid(),
  environmentId: z.uuid().nullable(),
  type: z.enum(NOTIFICATION_CHANNEL_TYPES),
  name: z.string(),
  config: z.record(z.string(), z.unknown()),
  isActive: z.boolean(),
  createdAt: z.string(),
  updatedAt: z.string(),
});
export type NotificationChannel = z.infer<typeof notificationChannelSchema>;
