import { z } from "zod";

export const NOTIFICATION_CHANNEL_TYPE = {
  EMAIL: "email",
  BASE_VN: "base_vn",
  TELEGRAM: "telegram",
  OTHER: "other",
} as const;
export type NotificationChannelType = (typeof NOTIFICATION_CHANNEL_TYPE)[keyof typeof NOTIFICATION_CHANNEL_TYPE];

export const notificationChannelSchema = z.object({
  id: z.uuid(),
  projectId: z.uuid(),
  environmentId: z.uuid().nullable(),
  type: z.enum([
    NOTIFICATION_CHANNEL_TYPE.EMAIL,
    NOTIFICATION_CHANNEL_TYPE.BASE_VN,
    NOTIFICATION_CHANNEL_TYPE.TELEGRAM,
    NOTIFICATION_CHANNEL_TYPE.OTHER,
  ]),
  name: z.string(),
  config: z.record(z.string(), z.unknown()),
  isActive: z.boolean(),
  createdAt: z.string(),
  updatedAt: z.string(),
});
export type NotificationChannel = z.infer<typeof notificationChannelSchema>;
