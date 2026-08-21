import { z } from "zod";

export {
  SYSTEM_ROLE_NAMES,
  isProtectedAdminRole,
  type SystemRoleName,
} from "@/shared/constants/roles";

export const permissionSchema = z.object({
  id: z.uuid(),
  resource: z.string(),
  action: z.string(),
  descriptionKey: z.string(),
});

export type PermissionItem = z.infer<typeof permissionSchema>;

export const roleSchema = z.object({
  id: z.uuid(),
  name: z.string(),
  isSystem: z.boolean(),
  permissions: z.array(permissionSchema),
});

export type Role = z.infer<typeof roleSchema>;

export const rolesPageSchema = z.object({
  items: z.array(roleSchema),
  total: z.number(),
  limit: z.number(),
  offset: z.number(),
});

export type RolesPage = z.infer<typeof rolesPageSchema>;

export const permissionsListSchema = z.array(permissionSchema);
export type PermissionsList = z.infer<typeof permissionsListSchema>;

export const userRolesAssignmentSchema = z.object({
  roleIds: z.array(z.uuid()),
});

export type UserRolesAssignment = z.infer<typeof userRolesAssignmentSchema>;
