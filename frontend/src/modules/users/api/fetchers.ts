import { apiFetch } from "@/shared/lib/api-client";
import { API_CONFIG } from "@/shared/constants/api";
import { userSchema, type User, type UserStatus } from "@/entities/user";
import { usersPageSchema, type UsersPage } from "../model/schema";

/**
 * Fetches a paginated list of users from GET /users.
 * Validates the response at runtime using `usersPageSchema`.
 */
export async function fetchUsers(limit = 50, offset = 0): Promise<UsersPage> {
  const raw = await apiFetch<unknown>(
    `${API_CONFIG.ENDPOINTS.USERS.ROOT}?limit=${limit}&offset=${offset}`,
  );
  return usersPageSchema.parse(raw);
}

/**
 * Updates a user's status via PATCH /users/{user_id}/status.
 * Returns the updated User object validated via `userSchema`.
 */
export async function updateUserStatus(
  userId: string,
  status: UserStatus,
): Promise<User> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.USERS.STATUS(userId), {
    method: "PATCH",
    data: { status },
  });
  return userSchema.parse(raw);
}

/**
 * Assigns multiple roles to a user via PUT /rbac/users/{userId}/roles.
 */
export async function assignUserRoles(userId: string, roleIds: string[]): Promise<void> {
  await apiFetch<unknown>(API_CONFIG.ENDPOINTS.RBAC.USER_ROLES(userId), {
    method: "PUT",
    data: { roleIds },
  });
}
