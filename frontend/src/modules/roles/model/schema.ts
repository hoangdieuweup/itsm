import { z } from "zod";

export const permissionSchema = z.object({
  id: z.number(),
  resource: z.string(),
  action: z.string(),
  descriptionKey: z.string(),
});

export type PermissionItem = z.infer<typeof permissionSchema>;

export const roleSchema = z.object({
  id: z.number(),
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
