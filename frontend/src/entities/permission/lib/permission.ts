import { AUTH_STATUS } from "@/shared/constants/auth";

export type Permission = `${string}.${string}`;

interface HasPermissions {
  status?: string;
  permissions?: readonly string[] | string[];
}

/**
 * Pure function to verify if a given permission set or session contains the specified resource and action.
 * Automatically verifies authentication status if an AuthSession object is passed.
 * Works uniformly in Server Components (SSR), Client Components, and API fetchers.
 */
export function hasPermission(
  source: HasPermissions | readonly string[] | string[] | null | undefined,
  resource: string,
  action: string,
): boolean {
  if (!source) {
    return false;
  }

  // If source is an AuthSession or session-like object
  if ("status" in source) {
    if (source.status !== AUTH_STATUS.AUTHENTICATED) {
      return false;
    }

    return Array.isArray(source.permissions)
      ? source.permissions.includes(`${resource}.${action}`)
      : false;
  }

  // If source is an object containing permissions array
  if ("permissions" in source && Array.isArray(source.permissions)) {
    return source.permissions.includes(`${resource}.${action}`);
  }

  // If source is an array of permission strings
  if (Array.isArray(source)) {
    return source.includes(`${resource}.${action}`);
  }

  return false;
}

