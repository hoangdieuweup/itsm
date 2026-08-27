import { z } from "zod";

export const logEntrySchema = z.object({
  timestamp: z.string(),
  line: z.string(),
  labels: z.record(z.string(), z.string()),
});
export type LogEntry = z.infer<typeof logEntrySchema>;

export const logQueryResultSchema = z.object({
  entries: z.array(logEntrySchema),
});

export const cloudflareTrafficBucketSchema = z.object({
  bucketStart: z.string(),
  requests: z.number(),
  bytes: z.number(),
});

export const cloudflareTrafficStatusCountSchema = z.object({
  status: z.number(),
  requests: z.number(),
});

export const cloudflareTrafficStatsSchema = z.object({
  hostname: z.string(),
  totalRequests: z.number(),
  totalBytes: z.number(),
  buckets: z.array(cloudflareTrafficBucketSchema),
  statusCodes: z.array(cloudflareTrafficStatusCountSchema),
});
export type CloudflareTrafficStats = z.infer<typeof cloudflareTrafficStatsSchema>;
