import { describe, expect, it } from "vitest";
import { incidentSchema } from "./schema";

describe("incidentSchema", () => {
  it("parses a manually-filed open incident with a null alert rule", () => {
    const parsed = incidentSchema.parse({
      id: "b3f1c2e4-1111-4444-8888-000000000000",
      projectId: "b3f1c2e4-2222-4444-8888-000000000000",
      environmentId: "b3f1c2e4-3333-4444-8888-000000000000",
      alertRuleId: null,
      source: "MANUAL",
      category: "TRAFFIC",
      severity: "MEDIUM",
      status: "OPEN",
      title: "Manually filed",
      logRefId: null,
      detectedAt: "2026-01-01T00:00:00Z",
      acknowledgedAt: null,
      acknowledgedBy: null,
      resolvedAt: null,
      resolvedBy: null,
      createdAt: "2026-01-01T00:00:00Z",
      updatedAt: "2026-01-01T00:00:00Z",
    });
    expect(parsed.status).toBe("OPEN");
    expect(parsed.alertRuleId).toBeNull();
  });
});
