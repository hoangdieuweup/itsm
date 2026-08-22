import { z } from "zod";

export const cloudflareAccountSchema = z.object({
  id: z.uuid(),
  label: z.string(),
  cfAccountId: z.string(),
  createdBy: z.uuid().nullable(),
  createdAt: z.string(),
  updatedAt: z.string(),
});

export type CloudflareAccount = z.infer<typeof cloudflareAccountSchema>;
