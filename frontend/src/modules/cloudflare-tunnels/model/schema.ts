import { z } from "zod";
import { MANAGED_BY } from "@/shared/constants/cloudflare";

export const TUNNEL_STATUS = {
  HEALTHY: "healthy",
  DEGRADED: "degraded",
  DOWN: "down",
  UNKNOWN: "unknown",
} as const;
export type TunnelStatus = (typeof TUNNEL_STATUS)[keyof typeof TUNNEL_STATUS];

export const cloudflareTunnelSchema = z.object({
  id: z.uuid(),
  cloudflareAccountId: z.uuid(),
  cfTunnelId: z.string(),
  name: z.string(),
  status: z.enum([TUNNEL_STATUS.HEALTHY, TUNNEL_STATUS.DEGRADED, TUNNEL_STATUS.DOWN, TUNNEL_STATUS.UNKNOWN]),
  lastSyncedAt: z.string().nullable(),
  createdAt: z.string(),
  updatedAt: z.string(),
});
export type CloudflareTunnel = z.infer<typeof cloudflareTunnelSchema>;

export const cloudflareTunnelCreateResponseSchema = z.object({
  tunnel: cloudflareTunnelSchema,
  token: z.string(),
});
export type CloudflareTunnelCreateResponse = z.infer<typeof cloudflareTunnelCreateResponseSchema>;

export const tunnelTokenResponseSchema = z.object({
  token: z.string(),
});

export const tunnelPublicHostnameSchema = z.object({
  id: z.uuid(),
  tunnelId: z.uuid(),
  environmentId: z.uuid().nullable(),
  hostname: z.string(),
  service: z.string(),
  managedBy: z.enum([MANAGED_BY.SYSTEM, MANAGED_BY.EXTERNAL]),
  createdBy: z.uuid().nullable(),
  createdAt: z.string(),
  updatedAt: z.string(),
});
export type TunnelPublicHostname = z.infer<typeof tunnelPublicHostnameSchema>;
