export const RESOURCES = {
  ROLE: "role",
  PERMISSION: "permission",
  USER: "user",
} as const;

export type Resource = (typeof RESOURCES)[keyof typeof RESOURCES];

export const ACTIONS = {
  CREATE: "create",
  READ: "read",
  UPDATE: "update",
  DELETE: "delete",
  UPDATE_STATUS: "update_status",
  ASSIGN_ROLE: "assign_role",
} as const;

export type Action = (typeof ACTIONS)[keyof typeof ACTIONS];

export const PERMISSIONS = {
  ROLE: {
    RESOURCE: RESOURCES.ROLE,
    CREATE: `${RESOURCES.ROLE}.${ACTIONS.CREATE}` as const,
    READ: `${RESOURCES.ROLE}.${ACTIONS.READ}` as const,
    UPDATE: `${RESOURCES.ROLE}.${ACTIONS.UPDATE}` as const,
    DELETE: `${RESOURCES.ROLE}.${ACTIONS.DELETE}` as const,
  },
  PERMISSION: {
    RESOURCE: RESOURCES.PERMISSION,
    READ: `${RESOURCES.PERMISSION}.${ACTIONS.READ}` as const,
  },
  USER: {
    RESOURCE: RESOURCES.USER,
    READ: `${RESOURCES.USER}.${ACTIONS.READ}` as const,
    UPDATE_STATUS: `${RESOURCES.USER}.${ACTIONS.UPDATE_STATUS}` as const,
    ASSIGN_ROLE: `${RESOURCES.USER}.${ACTIONS.ASSIGN_ROLE}` as const,
  },
} as const;
