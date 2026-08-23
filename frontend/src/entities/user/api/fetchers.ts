import { apiFetch } from "@/shared/lib/api-client";
import { API_CONFIG } from "@/shared/constants/api";
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
