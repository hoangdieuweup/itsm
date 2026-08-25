"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createDnsRecord,
  deleteDnsRecord,
  fetchDnsRecords,
  syncDnsRecords,
  updateDnsRecord,
  type DnsRecordFormValues,
  type DnsRecordUpdateValues,
} from "../api/fetchers";
import { cloudflareDnsKeys } from "../api/query-keys";
import { useToastMessage } from "@/shared/hooks/use-toast-message";

export function useDnsRecordsQuery(environmentId: string, enabled: boolean) {
  return useQuery({
    queryKey: cloudflareDnsKeys.records(environmentId),
    queryFn: () => fetchDnsRecords(environmentId),
    enabled,
  });
}

export function useSyncDnsRecords(environmentId: string) {
  const queryClient = useQueryClient();
  const { success, error } = useToastMessage("cloudflareDns");

  return useMutation({
    mutationFn: () => syncDnsRecords(environmentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: cloudflareDnsKeys.records(environmentId) });
      success("syncCompleted");
    },
    onError: error,
  });
}

export function useCreateDnsRecord(environmentId: string) {
  const queryClient = useQueryClient();
  const { success, error } = useToastMessage("cloudflareDns");

  return useMutation({
    mutationFn: (data: DnsRecordFormValues) => createDnsRecord(environmentId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: cloudflareDnsKeys.records(environmentId) });
      success("recordCreated");
    },
    onError: error,
  });
}

export function useUpdateDnsRecord(environmentId: string) {
  const queryClient = useQueryClient();
  const { success, error } = useToastMessage("cloudflareDns");

  return useMutation({
    mutationFn: ({ recordId, data }: { recordId: string; data: DnsRecordUpdateValues }) =>
      updateDnsRecord(environmentId, recordId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: cloudflareDnsKeys.records(environmentId) });
      success("recordUpdated");
    },
    onError: error,
  });
}

export function useDeleteDnsRecord(environmentId: string) {
  const queryClient = useQueryClient();
  const { success, error } = useToastMessage("cloudflareDns");

  return useMutation({
    mutationFn: (recordId: string) => deleteDnsRecord(environmentId, recordId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: cloudflareDnsKeys.records(environmentId) });
      success("recordDeleted");
    },
    onError: error,
  });
}
