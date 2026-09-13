import { z } from "zod";
import { ACCESS_LEVEL } from "@/shared/constants/cloudflare";

/** Mirrors the backend's CloudflareAccountManagerRead. */
export const cloudflareAccountManagerSchema = z.object({
  userId: z.uuid(),
  email: z.string(),
  name: z.string(),
  accessLevel: z.enum([ACCESS_LEVEL.OWNER, ACCESS_LEVEL.EDITOR, ACCESS_LEVEL.VIEWER]),
  createdAt: z.string(),
});
export type CloudflareAccountManager = z.infer<typeof cloudflareAccountManagerSchema>;

/** Response body of POST /cloudflare-accounts/{id}/reveal-token. */
export const revealedTokenSchema = z.object({
  apiToken: z.string(),
});
