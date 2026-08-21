export const RESOURCES = {
  ROLE: "role",
  PERMISSION: "permission",
  USER: "user",
  PROJECT: "project",
  ENVIRONMENT: "environment",
  AUDIT_LOG: "audit_log",
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
  PROJECT: {
    RESOURCE: RESOURCES.PROJECT,
    CREATE: `${RESOURCES.PROJECT}.${ACTIONS.CREATE}` as const,
    READ: `${RESOURCES.PROJECT}.${ACTIONS.READ}` as const,
    UPDATE: `${RESOURCES.PROJECT}.${ACTIONS.UPDATE}` as const,
    DELETE: `${RESOURCES.PROJECT}.${ACTIONS.DELETE}` as const,
  },
  ENVIRONMENT: {
    RESOURCE: RESOURCES.ENVIRONMENT,
    CREATE: `${RESOURCES.ENVIRONMENT}.${ACTIONS.CREATE}` as const,
    READ: `${RESOURCES.ENVIRONMENT}.${ACTIONS.READ}` as const,
    UPDATE: `${RESOURCES.ENVIRONMENT}.${ACTIONS.UPDATE}` as const,
    DELETE: `${RESOURCES.ENVIRONMENT}.${ACTIONS.DELETE}` as const,
  },
  AUDIT_LOG: {
    RESOURCE: RESOURCES.AUDIT_LOG,
    READ: `${RESOURCES.AUDIT_LOG}.${ACTIONS.READ}` as const,
  },
} as const;
