import { describe, expect, it } from "vitest";
import { lokiConfigSchema } from "./schema";

describe("lokiConfigSchema", () => {
  it("parses a config without a raw credential field", () => {
    const parsed = lokiConfigSchema.parse({
      id: "b3f1c2e4-1111-4444-8888-000000000000",
      environmentId: "b3f1c2e4-2222-4444-8888-000000000000",
      endpointUrl: "http://loki:3100",
      tenantId: null,
      authType: "bearer",
      hasCredential: true,
      defaultQuery: '{job="api"}',
      defaultRangeMinutes: 60,
      createdAt: "2026-01-01T00:00:00Z",
      updatedAt: "2026-01-01T00:00:00Z",
    });
    expect(parsed.hasCredential).toBe(true);
    expect(parsed.authType).toBe("bearer");
  });
});
