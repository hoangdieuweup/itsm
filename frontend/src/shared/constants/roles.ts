export const SYSTEM_ROLE_NAMES = {
  ADMIN: "admin",
  MEMBER: "member",
} as const;

export type SystemRoleName =
  (typeof SYSTEM_ROLE_NAMES)[keyof typeof SYSTEM_ROLE_NAMES];

/**
 * Checks if a role or role name represents the protected system Admin role
 * whose permissions are permanently immutable.
 */
export function isProtectedAdminRole(
  role: { name?: string | null; isSystem?: boolean } | string | null | undefined,
): boolean {
  if (!role) return false;
  const roleName = typeof role === "string" ? role : role.name;
  return roleName === SYSTEM_ROLE_NAMES.ADMIN;
}
