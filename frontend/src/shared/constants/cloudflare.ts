export const MANAGED_BY = {
  SYSTEM: "system",
  EXTERNAL: "external",
} as const;
export type ManagedBy = (typeof MANAGED_BY)[keyof typeof MANAGED_BY];
