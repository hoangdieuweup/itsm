import { describe, expect, it } from "vitest";
import { cloudflareConfigSchema } from "./schema";

describe("cloudflareConfigSchema", () => {
  it("parses a bound environment's Cloudflare config", () => {
    const parsed = cloudflareConfigSchema.parse({
      id: "b3f1c2e4-1111-4444-8888-000000000000",
      environmentId: "b3f1c2e4-2222-4444-8888-000000000000",
      cloudflareAccountId: "b3f1c2e4-3333-4444-8888-000000000000",
      zoneId: "z1",
      zoneName: "example.com",
      createdAt: "2026-01-01T00:00:00Z",
      updatedAt: "2026-01-01T00:00:00Z",
    });
    expect(parsed.zoneName).toBe("example.com");
  });
});
