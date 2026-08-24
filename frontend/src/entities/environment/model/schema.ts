import { z } from "zod";

export const ENVIRONMENT_TYPE = {
  DEV: "dev",
  STAGING: "staging",
  PRODUCTION: "production",
} as const;
export type EnvironmentType = (typeof ENVIRONMENT_TYPE)[keyof typeof ENVIRONMENT_TYPE];

export const environmentSchema = z.object({
  id: z.uuid(),
  projectId: z.uuid(),
  type: z.enum([ENVIRONMENT_TYPE.DEV, ENVIRONMENT_TYPE.STAGING, ENVIRONMENT_TYPE.PRODUCTION]),
  name: z.string(),
  baseUrl: z.string().nullable(),
  createdAt: z.string(),
  updatedAt: z.string(),
});

export type Environment = z.infer<typeof environmentSchema>;
