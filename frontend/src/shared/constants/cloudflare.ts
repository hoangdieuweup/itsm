export const MANAGED_BY = {
  SYSTEM: "system",
  EXTERNAL: "external",
} as const;
export type ManagedBy = (typeof MANAGED_BY)[keyof typeof MANAGED_BY];

export const ACCESS_LEVEL = {
  OWNER: "owner",
  EDITOR: "editor",
  VIEWER: "viewer",
} as const;
export type AccessLevel = (typeof ACCESS_LEVEL)[keyof typeof ACCESS_LEVEL];
