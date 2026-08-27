import { describe, expect, it } from "vitest";
import { logEntrySchema } from "./schema";

describe("logEntrySchema", () => {
  it("parses a flattened Loki entry", () => {
    const parsed = logEntrySchema.parse({
      timestamp: "1700000000000000000",
      line: "hello",
      labels: { job: "api" },
    });
    expect(parsed.line).toBe("hello");
  });
});
