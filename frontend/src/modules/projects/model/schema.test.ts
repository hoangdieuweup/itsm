import { describe, expect, it } from "vitest";
import { projectLinkSchema, projectMemberSchema, projectRoleSchema } from "./schema";

const ID = "b3f1c2e4-1111-4444-8888-000000000000";
const OTHER_ID = "b3f1c2e4-2222-4444-8888-000000000000";
const TIMESTAMP = "2026-01-01T00:00:00Z";

describe("projects model schemas", () => {
  it("parses a link and drops backend-only timestamps", () => {
    const parsed = projectLinkSchema.parse({
      id: ID,
      projectId: OTHER_ID,
      type: "jira",
      name: "Board",
      url: "https://example.atlassian.net",
      isDefault: true,
      createdAt: TIMESTAMP,
      updatedAt: TIMESTAMP,
    });

    expect(parsed).toEqual({
      id: ID,
      projectId: OTHER_ID,
      type: "jira",
      name: "Board",
      url: "https://example.atlassian.net",
      isDefault: true,
    });
  });

  it("rejects a link type the backend does not define", () => {
    expect(() =>
      projectLinkSchema.parse({
        id: ID,
        projectId: OTHER_ID,
        type: "slack",
        name: "Chat",
        url: "https://slack.com",
        isDefault: false,
      }),
    ).toThrow();
  });

  it("parses a member with no project role", () => {
    const parsed = projectMemberSchema.parse({
      userId: ID,
      name: "Ada",
      email: "ada@example.com",
      createdAt: TIMESTAMP,
      projectRoleId: null,
      projectRoleName: null,
    });

    expect(parsed.projectRoleId).toBeNull();
    expect(parsed.projectRoleName).toBeNull();
  });

  it("parses a role together with its permissions", () => {
    const parsed = projectRoleSchema.parse({
      id: ID,
      projectId: OTHER_ID,
      name: "Operators",
      permissions: [
        {
          id: OTHER_ID,
          resource: "project_incident",
          action: "read",
          descriptionKey: "permissions.project_incident.read",
        },
      ],
      createdAt: TIMESTAMP,
      updatedAt: TIMESTAMP,
    });

    expect(parsed.permissions).toHaveLength(1);
    expect(parsed.permissions[0]?.resource).toBe("project_incident");
  });
});
