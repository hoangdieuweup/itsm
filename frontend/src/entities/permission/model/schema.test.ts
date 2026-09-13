import { describe, expect, it } from "vitest";
import { projectPermissionSetSchema } from "./schema";

const PROJECT_ID = "b3f1c2e4-1111-4444-8888-000000000000";

describe("projectPermissionSetSchema", () => {
  it("parses GET /projects/{id}/permissions", () => {
    const parsed = projectPermissionSetSchema.parse({
      projectId: PROJECT_ID,
      permissions: ["project_incident.read", "environment.read"],
    });

    expect(parsed.permissions).toEqual(["project_incident.read", "environment.read"]);
  });

  it("rejects a payload without a permissions array", () => {
    expect(() => projectPermissionSetSchema.parse({ projectId: PROJECT_ID })).toThrow();
  });
});
