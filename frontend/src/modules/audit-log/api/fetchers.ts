import { z } from "zod";
import { apiFetch } from "@/shared/lib/api-client";
import { API_CONFIG } from "@/shared/constants/api";

export const AUDIT_EVENT_TYPES = ["AUDIT", "INCIDENT_DETECTION", "NOTIFICATION_SENT"] as const;

export const auditLogEntrySchema = z.object({
  id: z.string(),
  type: z.enum(AUDIT_EVENT_TYPES),
  projectId: z.uuid().nullable(),
  environmentId: z.uuid().nullable(),
  source: z.string(),
  actor: z.object({ userId: z.uuid().nullable(), email: z.string().nullable() }),
  action: z.string(),
  severity: z.string(),
  incidentId: z.string().nullable(),
  message: z.string(),
  payload: z.record(z.string(), z.unknown()),
  timestamp: z.string(),
  createdAt: z.string(),
});

export type AuditLogEntry = z.infer<typeof auditLogEntrySchema>;

export const auditLogsPageSchema = z.object({
  items: z.array(auditLogEntrySchema),
  total: z.number(),
  limit: z.number(),
  offset: z.number(),
});

export type AuditLogsPage = z.infer<typeof auditLogsPageSchema>;

export interface AuditLogFilters {
  projectId?: string;
  environmentId?: string;
  type?: (typeof AUDIT_EVENT_TYPES)[number];
  since?: string;
  until?: string;
  limit?: number;
  offset?: number;
}

export async function fetchAuditLogs(filters: AuditLogFilters = {}): Promise<AuditLogsPage> {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(filters)) {
    if (value !== undefined) params.set(key, String(value));
  }
  const query = params.toString();
  const raw = await apiFetch<unknown>(
    `${API_CONFIG.ENDPOINTS.AUDIT_LOGS.ROOT}${query ? `?${query}` : ""}`,
  );
  return auditLogsPageSchema.parse(raw);
}
