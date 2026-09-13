import { z } from "zod";

/** Mirrors the backend's ProjectPermissionSetRead (GET /projects/{id}/permissions). */
export const projectPermissionSetSchema = z.object({
  projectId: z.uuid(),
  permissions: z.array(z.string()),
});
export type ProjectPermissionSet = z.infer<typeof projectPermissionSetSchema>;
