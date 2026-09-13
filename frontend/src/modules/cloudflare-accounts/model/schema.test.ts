import { describe, expect, it } from "vitest";
import { cloudflareAccountManagerSchema, revealedTokenSchema } from "./schema";

const MANAGER = {
  userId: "b3f1c2e4-1111-4444-8888-000000000000",
  email: "ada@example.com",
  name: "Ada",
  accessLevel: "editor",
  createdAt: "2026-01-01T00:00:00Z",
};

describe("cloudflare-accounts model schemas", () => {
  it("parses a manager row", () => {
    expect(cloudflareAccountManagerSchema.parse(MANAGER).accessLevel).toBe("editor");
  });

  it("rejects an access level the backend does not define", () => {
    expect(() => cloudflareAccountManagerSchema.parse({ ...MANAGER, accessLevel: "admin" })).toThrow();
  });

  it("parses a revealed token", () => {
    expect(revealedTokenSchema.parse({ apiToken: "token" }).apiToken).toBe("token");
  });
});
