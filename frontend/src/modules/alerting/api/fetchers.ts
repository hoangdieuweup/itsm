import { apiFetch } from "@/shared/lib/api-client";
import { API_CONFIG } from "@/shared/constants/api";
import {
  alertRuleSchema,
  availableAlertOptionSchema,
  type AlertRule,
  type AlertRuleSource,
} from "../model/schema";

export interface AlertRuleFormValues {
  name: string;
  source: AlertRuleSource;
  cfAlertType?: string | null;
  condition?: Record<string, unknown> | null;
  severity: string;
  channelIds: string[];
}

export async function fetchAlertRules(environmentId: string): Promise<AlertRule[]> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.ALERT_RULES.ROOT(environmentId));
  return alertRuleSchema.array().parse(raw);
}

export async function fetchAvailableAlerts(accountId: string) {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.ALERT_RULES.AVAILABLE_ALERTS(accountId));
  return availableAlertOptionSchema.array().parse(raw);
}

export async function createAlertRule(environmentId: string, data: AlertRuleFormValues): Promise<AlertRule> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.ALERT_RULES.ROOT(environmentId), {
    method: "POST",
    data,
  });
  return alertRuleSchema.parse(raw);
}

export async function updateAlertRule(
  id: string,
  data: Partial<Pick<AlertRuleFormValues, "name" | "severity" | "channelIds">> & { isActive?: boolean },
): Promise<AlertRule> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.ALERT_RULES.DETAIL(id), { method: "PATCH", data });
  return alertRuleSchema.parse(raw);
}

export async function deleteAlertRule(id: string): Promise<void> {
  await apiFetch<unknown>(API_CONFIG.ENDPOINTS.ALERT_RULES.DETAIL(id), { method: "DELETE" });
}
