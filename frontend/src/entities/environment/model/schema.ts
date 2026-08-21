import { z } from "zod";

export const ENVIRONMENT_TYPES = ["dev", "staging", "production"] as const;
export type EnvironmentType = (typeof ENVIRONMENT_TYPES)[number];

export const environmentSchema = z.object({
  id: z.uuid(),
  projectId: z.uuid(),
  type: z.enum(ENVIRONMENT_TYPES),
  name: z.string(),
  baseUrl: z.string().nullable(),
  createdAt: z.string(),
  updatedAt: z.string(),
});

export type Environment = z.infer<typeof environmentSchema>;
