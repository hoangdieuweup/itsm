import { z } from "zod";
import { permissionSchema } from "@/entities/role";

export const PROJECT_LINK_TYPE = {
  JIRA: "jira",
  GIT: "git",
  OTHER: "other",
} as const;
export type ProjectLinkType = (typeof PROJECT_LINK_TYPE)[keyof typeof PROJECT_LINK_TYPE];

/** Mirrors the backend's ProjectLinkRead (timestamps are not used by the UI). */
export const projectLinkSchema = z.object({
  id: z.uuid(),
  projectId: z.uuid(),
  type: z.enum([PROJECT_LINK_TYPE.JIRA, PROJECT_LINK_TYPE.GIT, PROJECT_LINK_TYPE.OTHER]),
  name: z.string(),
  url: z.string(),
  isDefault: z.boolean(),
});
export type ProjectLink = z.infer<typeof projectLinkSchema>;

/** Mirrors the backend's ProjectMemberRead. */
export const projectMemberSchema = z.object({
  userId: z.uuid(),
  name: z.string(),
  email: z.string(),
  createdAt: z.string(),
  projectRoleId: z.uuid().nullish(),
  projectRoleName: z.string().nullish(),
});
export type ProjectMember = z.infer<typeof projectMemberSchema>;

/** Mirrors the backend's ProjectRoleRead (timestamps are not used by the UI). */
export const projectRoleSchema = z.object({
  id: z.uuid(),
  projectId: z.uuid(),
  name: z.string(),
  permissions: z.array(permissionSchema),
});
export type ProjectRole = z.infer<typeof projectRoleSchema>;
