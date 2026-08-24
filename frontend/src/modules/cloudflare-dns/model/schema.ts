import { z } from "zod";
import { MANAGED_BY } from "@/shared/constants/cloudflare";

export const DNS_RECORD_TYPE = {
  A: "A",
  AAAA: "AAAA",
  CNAME: "CNAME",
  TXT: "TXT",
  MX: "MX",
  OTHER: "OTHER",
} as const;
export type DnsRecordType = (typeof DNS_RECORD_TYPE)[keyof typeof DNS_RECORD_TYPE];

export const zoneOptionSchema = z.object({
  id: z.string(),
  name: z.string(),
});
export type ZoneOption = z.infer<typeof zoneOptionSchema>;

export const dnsRecordSchema = z.object({
  id: z.uuid(),
  environmentId: z.uuid(),
  cfRecordId: z.string(),
  recordType: z.enum([
    DNS_RECORD_TYPE.A,
    DNS_RECORD_TYPE.AAAA,
    DNS_RECORD_TYPE.CNAME,
    DNS_RECORD_TYPE.TXT,
    DNS_RECORD_TYPE.MX,
    DNS_RECORD_TYPE.OTHER,
  ]),
  name: z.string(),
  content: z.string(),
  priority: z.number().nullable(),
  proxied: z.boolean(),
  ttl: z.number(),
  managedBy: z.enum([MANAGED_BY.SYSTEM, MANAGED_BY.EXTERNAL]),
  createdBy: z.uuid().nullable(),
  createdAt: z.string(),
  updatedAt: z.string(),
});
export type DnsRecord = z.infer<typeof dnsRecordSchema>;
