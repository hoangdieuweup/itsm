import { z } from "zod";

export const INCIDENT_SOURCE = { CLOUDFLARE: "CLOUDFLARE", LOKI: "LOKI", MANUAL: "MANUAL" } as const;
export type IncidentSource = (typeof INCIDENT_SOURCE)[keyof typeof INCIDENT_SOURCE];

export const INCIDENT_CATEGORY = {
  TRAFFIC: "TRAFFIC",
  DDOS: "DDOS",
  ORIGIN_ERROR: "ORIGIN_ERROR",
  DNS_DRIFT: "DNS_DRIFT",
  TUNNEL_DRIFT: "TUNNEL_DRIFT",
  LOG_MATCH: "LOG_MATCH",
  MANUAL: "MANUAL",
} as const;
export type IncidentCategory = (typeof INCIDENT_CATEGORY)[keyof typeof INCIDENT_CATEGORY];

export const ALERT_SEVERITY = { LOW: "LOW", MEDIUM: "MEDIUM", HIGH: "HIGH", CRITICAL: "CRITICAL" } as const;
export type AlertSeverity = (typeof ALERT_SEVERITY)[keyof typeof ALERT_SEVERITY];

export const INCIDENT_STATUS = { OPEN: "OPEN", ACKNOWLEDGED: "ACKNOWLEDGED", RESOLVED: "RESOLVED" } as const;
export type IncidentStatus = (typeof INCIDENT_STATUS)[keyof typeof INCIDENT_STATUS];

export const incidentSchema = z.object({
  id: z.uuid(),
  projectId: z.uuid(),
  environmentId: z.uuid(),
  alertRuleId: z.uuid().nullable(),
  source: z.enum([INCIDENT_SOURCE.CLOUDFLARE, INCIDENT_SOURCE.LOKI, INCIDENT_SOURCE.MANUAL]),
  category: z.enum([
    INCIDENT_CATEGORY.TRAFFIC,
    INCIDENT_CATEGORY.DDOS,
    INCIDENT_CATEGORY.ORIGIN_ERROR,
    INCIDENT_CATEGORY.DNS_DRIFT,
    INCIDENT_CATEGORY.TUNNEL_DRIFT,
    INCIDENT_CATEGORY.LOG_MATCH,
    INCIDENT_CATEGORY.MANUAL,
  ]),
  severity: z.enum([ALERT_SEVERITY.LOW, ALERT_SEVERITY.MEDIUM, ALERT_SEVERITY.HIGH, ALERT_SEVERITY.CRITICAL]),
  status: z.enum([INCIDENT_STATUS.OPEN, INCIDENT_STATUS.ACKNOWLEDGED, INCIDENT_STATUS.RESOLVED]),
  title: z.string(),
  logRefId: z.string().nullable(),
  detectedAt: z.string(),
  acknowledgedAt: z.string().nullable(),
  acknowledgedBy: z.uuid().nullable(),
  resolvedAt: z.string().nullable(),
  resolvedBy: z.uuid().nullable(),
  createdAt: z.string(),
  updatedAt: z.string(),
});
export type Incident = z.infer<typeof incidentSchema>;
