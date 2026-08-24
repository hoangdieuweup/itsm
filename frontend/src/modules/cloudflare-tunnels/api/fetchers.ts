import { apiFetch } from "@/shared/lib/api-client";
import { API_CONFIG } from "@/shared/constants/api";
import {
  cloudflareTunnelSchema,
  cloudflareTunnelCreateResponseSchema,
  tunnelPublicHostnameSchema,
  tunnelTokenResponseSchema,
  type CloudflareTunnel,
  type CloudflareTunnelCreateResponse,
  type TunnelPublicHostname,
} from "../model/schema";

export async function fetchTunnels(environmentId: string): Promise<CloudflareTunnel[]> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.CLOUDFLARE_TUNNELS.ROOT(environmentId));
  return cloudflareTunnelSchema.array().parse(raw);
}

export async function syncTunnels(environmentId: string): Promise<CloudflareTunnel[]> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.CLOUDFLARE_TUNNELS.SYNC(environmentId), {
    method: "POST",
  });
  return cloudflareTunnelSchema.array().parse(raw);
}

export async function createTunnel(
  environmentId: string,
  name: string,
): Promise<CloudflareTunnelCreateResponse> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.CLOUDFLARE_TUNNELS.ROOT(environmentId), {
    method: "POST",
    data: { name },
  });
  return cloudflareTunnelCreateResponseSchema.parse(raw);
}

export async function deleteTunnel(environmentId: string, tunnelId: string): Promise<void> {
  await apiFetch<unknown>(API_CONFIG.ENDPOINTS.CLOUDFLARE_TUNNELS.DETAIL(environmentId, tunnelId), {
    method: "DELETE",
  });
}

export async function revealTunnelToken(environmentId: string, tunnelId: string): Promise<string> {
  const raw = await apiFetch<unknown>(
    API_CONFIG.ENDPOINTS.CLOUDFLARE_TUNNELS.REVEAL_TOKEN(environmentId, tunnelId),
    { method: "POST" },
  );
  return tunnelTokenResponseSchema.parse(raw).token;
}

export async function refreshTunnelStatus(environmentId: string, tunnelId: string): Promise<CloudflareTunnel> {
  const raw = await apiFetch<unknown>(
    API_CONFIG.ENDPOINTS.CLOUDFLARE_TUNNELS.REFRESH_STATUS(environmentId, tunnelId),
    { method: "POST" },
  );
  return cloudflareTunnelSchema.parse(raw);
}

export async function fetchTunnelHostnames(
  environmentId: string,
  tunnelId: string,
): Promise<TunnelPublicHostname[]> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.CLOUDFLARE_TUNNELS.HOSTNAMES(environmentId, tunnelId));
  return tunnelPublicHostnameSchema.array().parse(raw);
}

export async function addTunnelHostname(
  environmentId: string,
  tunnelId: string,
  data: { hostname: string; service: string },
): Promise<TunnelPublicHostname> {
  const raw = await apiFetch<unknown>(API_CONFIG.ENDPOINTS.CLOUDFLARE_TUNNELS.HOSTNAMES(environmentId, tunnelId), {
    method: "POST",
    data,
  });
  return tunnelPublicHostnameSchema.parse(raw);
}

export async function updateTunnelHostname(
  environmentId: string,
  tunnelId: string,
  hostnameId: string,
  service: string,
): Promise<TunnelPublicHostname> {
  const raw = await apiFetch<unknown>(
    API_CONFIG.ENDPOINTS.CLOUDFLARE_TUNNELS.HOSTNAME_DETAIL(environmentId, tunnelId, hostnameId),
    { method: "PATCH", data: { service } },
  );
  return tunnelPublicHostnameSchema.parse(raw);
}

export async function removeTunnelHostname(
  environmentId: string,
  tunnelId: string,
  hostnameId: string,
): Promise<void> {
  await apiFetch<unknown>(
    API_CONFIG.ENDPOINTS.CLOUDFLARE_TUNNELS.HOSTNAME_DETAIL(environmentId, tunnelId, hostnameId),
    { method: "DELETE" },
  );
}
