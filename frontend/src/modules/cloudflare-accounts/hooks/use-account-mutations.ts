"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { toast } from "sonner";
import { apiFetch } from "@/shared/lib/api-client";
import { API_CONFIG } from "@/shared/constants/api";
import { cloudflareAccountsKeys } from "@/entities/cloudflare-account";

/* ── Tunnel mutations ── */

export function useCreateAccountTunnel(accountId: string) {
  const qc = useQueryClient();
  const t = useTranslations("cloudflareAccounts");
  return useMutation({
    mutationFn: (name: string) =>
      apiFetch<{ cf_tunnel_id: string; token: string }>(
        API_CONFIG.ENDPOINTS.CLOUDFLARE_ACCOUNTS.TUNNELS(accountId),
        { method: "POST", data: { name } },
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: cloudflareAccountsKeys.tunnels(accountId) });
      toast.success(t("messages.tunnelCreated"));
    },
  });
}

export function useDeleteAccountTunnel(accountId: string) {
  const qc = useQueryClient();
  const t = useTranslations("cloudflareAccounts");
  return useMutation({
    mutationFn: (cfTunnelId: string) =>
      apiFetch<null>(
        API_CONFIG.ENDPOINTS.CLOUDFLARE_ACCOUNTS.TUNNEL_DETAIL(accountId, cfTunnelId),
        { method: "DELETE" },
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: cloudflareAccountsKeys.tunnels(accountId) });
      toast.success(t("messages.tunnelDeleted"));
    },
  });
}

/* ── DNS mutations ── */

interface DnsRecordPayload {
  record_type: string;
  name: string;
  content: string;
  ttl: number;
  proxied: boolean;
  priority?: number | null;
}

export function useCreateAccountDnsRecord(accountId: string, zoneId: string) {
  const qc = useQueryClient();
  const t = useTranslations("cloudflareAccounts");
  return useMutation({
    mutationFn: (payload: DnsRecordPayload) =>
      apiFetch<{ cf_record_id: string }>(
        API_CONFIG.ENDPOINTS.CLOUDFLARE_ACCOUNTS.ZONE_DNS_RECORDS(accountId, zoneId),
        { method: "POST", data: payload },
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: cloudflareAccountsKeys.zoneDnsRecords(accountId, zoneId) });
      toast.success(t("messages.dnsCreated"));
    },
  });
}

export function useUpdateAccountDnsRecord(accountId: string, zoneId: string) {
  const qc = useQueryClient();
  const t = useTranslations("cloudflareAccounts");
  return useMutation({
    mutationFn: ({ cfRecordId, ...payload }: DnsRecordPayload & { cfRecordId: string }) =>
      apiFetch<null>(
        API_CONFIG.ENDPOINTS.CLOUDFLARE_ACCOUNTS.ZONE_DNS_RECORD_DETAIL(accountId, zoneId, cfRecordId),
        { method: "PATCH", data: payload },
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: cloudflareAccountsKeys.zoneDnsRecords(accountId, zoneId) });
      toast.success(t("messages.dnsUpdated"));
    },
  });
}

export function useDeleteAccountDnsRecord(accountId: string, zoneId: string) {
  const qc = useQueryClient();
  const t = useTranslations("cloudflareAccounts");
  return useMutation({
    mutationFn: (cfRecordId: string) =>
      apiFetch<null>(
        API_CONFIG.ENDPOINTS.CLOUDFLARE_ACCOUNTS.ZONE_DNS_RECORD_DETAIL(accountId, zoneId, cfRecordId),
        { method: "DELETE" },
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: cloudflareAccountsKeys.zoneDnsRecords(accountId, zoneId) });
      toast.success(t("messages.dnsDeleted"));
    },
  });
}
