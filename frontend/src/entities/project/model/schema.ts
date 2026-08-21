import { z } from "zod";

export const projectSchema = z.object({
  id: z.uuid(),
  name: z.string(),
  description: z.string().nullable(),
  createdBy: z.uuid().nullable(),
  createdAt: z.string(),
  updatedAt: z.string(),
});

export type Project = z.infer<typeof projectSchema>;

export const projectsPageSchema = z.object({
  items: z.array(projectSchema),
  total: z.number(),
  limit: z.number(),
  offset: z.number(),
});

export type ProjectsPage = z.infer<typeof projectsPageSchema>;
