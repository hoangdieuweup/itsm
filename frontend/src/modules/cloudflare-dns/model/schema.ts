import { z } from "zod";

export const DNS_RECORD_TYPES = ["A", "AAAA", "CNAME", "TXT", "MX", "OTHER"] as const;

export const zoneOptionSchema = z.object({
  id: z.string(),
  name: z.string(),
});
export type ZoneOption = z.infer<typeof zoneOptionSchema>;

export const cloudflareConfigSchema = z.object({
  id: z.uuid(),
  environmentId: z.uuid(),
  cloudflareAccountId: z.uuid(),
  zoneId: z.string(),
  zoneName: z.string(),
  createdAt: z.string(),
  updatedAt: z.string(),
});
export type CloudflareConfig = z.infer<typeof cloudflareConfigSchema>;

export const dnsRecordSchema = z.object({
  id: z.uuid(),
  environmentId: z.uuid(),
  cfRecordId: z.string(),
  recordType: z.enum(DNS_RECORD_TYPES),
  name: z.string(),
  content: z.string(),
  priority: z.number().nullable(),
  proxied: z.boolean(),
  ttl: z.number(),
  managedBy: z.enum(["system", "external"]),
  createdBy: z.uuid().nullable(),
  createdAt: z.string(),
  updatedAt: z.string(),
});
export type DnsRecord = z.infer<typeof dnsRecordSchema>;
export type DnsRecordType = (typeof DNS_RECORD_TYPES)[number];
