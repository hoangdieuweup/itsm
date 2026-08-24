import { z } from "zod";

export const ALERT_RULE_SOURCE = { CLOUDFLARE_NATIVE: "CLOUDFLARE_NATIVE", LOKI_QUERY: "LOKI_QUERY" } as const;
export type AlertRuleSource = (typeof ALERT_RULE_SOURCE)[keyof typeof ALERT_RULE_SOURCE];

export const availableAlertOptionSchema = z.object({ alertType: z.string(), displayName: z.string() });
export type AvailableAlertOption = z.infer<typeof availableAlertOptionSchema>;

export const alertRuleSchema = z.object({
  id: z.uuid(),
  environmentId: z.uuid(),
  name: z.string(),
  source: z.enum([ALERT_RULE_SOURCE.CLOUDFLARE_NATIVE, ALERT_RULE_SOURCE.LOKI_QUERY]),
  cfAlertType: z.string().nullable(),
  cfPolicyId: z.string().nullable(),
  condition: z.record(z.string(), z.unknown()).nullable(),
  severity: z.enum(["LOW", "MEDIUM", "HIGH", "CRITICAL"]),
  isActive: z.boolean(),
  channelIds: z.array(z.uuid()),
  createdAt: z.string(),
  updatedAt: z.string(),
});
export type AlertRule = z.infer<typeof alertRuleSchema>;
