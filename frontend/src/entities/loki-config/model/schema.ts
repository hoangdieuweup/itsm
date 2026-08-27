import { z } from "zod";

export const LOKI_AUTH_TYPE = {
  NONE: "none",
  BASIC: "basic",
  BEARER: "bearer",
} as const;
export type LokiAuthType = (typeof LOKI_AUTH_TYPE)[keyof typeof LOKI_AUTH_TYPE];

export const lokiConfigSchema = z.object({
  id: z.uuid(),
  environmentId: z.uuid(),
  endpointUrl: z.string(),
  tenantId: z.string().nullable(),
  authType: z.enum([LOKI_AUTH_TYPE.NONE, LOKI_AUTH_TYPE.BASIC, LOKI_AUTH_TYPE.BEARER]),
  hasCredential: z.boolean(),
  defaultQuery: z.string(),
  defaultRangeMinutes: z.number(),
  createdAt: z.string(),
  updatedAt: z.string(),
});
export type LokiConfig = z.infer<typeof lokiConfigSchema>;
