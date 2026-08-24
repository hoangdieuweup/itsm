import { describe, expect, it } from "vitest";
import { notificationChannelSchema } from "./schema";

describe("notificationChannelSchema", () => {
  it("parses a telegram channel with masked config", () => {
    const parsed = notificationChannelSchema.parse({
      id: "b3f1c2e4-1111-4444-8888-000000000000",
      projectId: "b3f1c2e4-2222-4444-8888-000000000000",
      environmentId: null,
      type: "telegram",
      name: "Ops Alerts",
      config: { chatId: "1", hasBotToken: true },
      isActive: true,
      createdAt: "2026-01-01T00:00:00Z",
      updatedAt: "2026-01-01T00:00:00Z",
    });
    expect(parsed.type).toBe("telegram");
  });
});
