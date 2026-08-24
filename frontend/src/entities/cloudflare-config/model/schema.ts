import { z } from "zod";

export const cloudflareConfigSchema = z.object({
  id: z.uuid(),
  environmentId: z.uuid(),
  cloudflareAccountId: z.uuid(),
  zoneId: z.string(),
  zoneName: z.string(),
  createdAt: z.string(),
  updatedAt: z.string(),
});
export type CloudflareConfig = z.infer<typeof cloudflareConfigSchema>;
