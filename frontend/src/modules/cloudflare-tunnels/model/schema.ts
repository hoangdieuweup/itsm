import { z } from "zod";

export const TUNNEL_STATUSES = ["healthy", "degraded", "down", "unknown"] as const;

export const cloudflareTunnelSchema = z.object({
  id: z.uuid(),
  environmentId: z.uuid(),
  cfTunnelId: z.string(),
  name: z.string(),
  status: z.enum(TUNNEL_STATUSES),
  lastSyncedAt: z.string().nullable(),
  createdAt: z.string(),
  updatedAt: z.string(),
});
export type CloudflareTunnel = z.infer<typeof cloudflareTunnelSchema>;
export type TunnelStatus = (typeof TUNNEL_STATUSES)[number];

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
  hostname: z.string(),
  service: z.string(),
  managedBy: z.enum(["system", "external"]),
  createdBy: z.uuid().nullable(),
  createdAt: z.string(),
  updatedAt: z.string(),
});
export type TunnelPublicHostname = z.infer<typeof tunnelPublicHostnameSchema>;
