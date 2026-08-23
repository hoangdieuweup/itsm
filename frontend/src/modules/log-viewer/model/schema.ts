import { z } from "zod";

export const LOKI_AUTH_TYPES = ["none", "basic", "bearer"] as const;
export type LokiAuthType = (typeof LOKI_AUTH_TYPES)[number];

export const lokiConfigSchema = z.object({
  id: z.uuid(),
  environmentId: z.uuid(),
  endpointUrl: z.string(),
  tenantId: z.string().nullable(),
  authType: z.enum(LOKI_AUTH_TYPES),
  hasCredential: z.boolean(),
  defaultQuery: z.string(),
  defaultRangeMinutes: z.number(),
  createdAt: z.string(),
  updatedAt: z.string(),
});
export type LokiConfig = z.infer<typeof lokiConfigSchema>;

export const logEntrySchema = z.object({
  timestamp: z.string(),
  line: z.string(),
  labels: z.record(z.string(), z.string()),
});
export type LogEntry = z.infer<typeof logEntrySchema>;

export const logQueryResultSchema = z.object({
  entries: z.array(logEntrySchema),
});

export const cloudflareAuditLogEntrySchema = z.object({
  id: z.string(),
  when: z.string(),
  actorEmail: z.string().nullable(),
  actorIp: z.string().nullable(),
  actionType: z.string(),
  resourceType: z.string().nullable(),
  resourceProduct: z.string().nullable(),
  newValue: z.string().nullable(),
});
export type CloudflareAuditLogEntry = z.infer<typeof cloudflareAuditLogEntrySchema>;
