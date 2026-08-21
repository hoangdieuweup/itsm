import { z } from "zod";
import { userSchema, userStatusSchema, type UserStatus } from "@/entities/user";

/**
 * Zod schema for paginated users list response from GET /users.
 * Derived from backend's Page[UserRead].
 */
export const usersPageSchema = z.object({
  items: z.array(userSchema),
  total: z.number(),
  limit: z.number(),
  offset: z.number(),
});

export type UsersPage = z.infer<typeof usersPageSchema>;

export { userStatusSchema, type UserStatus };
