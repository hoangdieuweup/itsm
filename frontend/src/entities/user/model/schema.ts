import { z } from "zod";

/**
 * Structural skeleton only — field list will be finalized once the SSO
 * integration sub-issue (#5) confirms the DX user-sync payload shape.
 */
export const userSchema = z.object({
  id: z.string(),
  name: z.string(),
  email: z.string().email(),
  avatarUrl: z.string().url().nullable().optional(),
  role: z.string(),
});

export type User = z.infer<typeof userSchema>;
