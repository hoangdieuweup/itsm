"use client";

import { useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { Cloud, Globe, Plus, Pencil, Trash2, ExternalLink } from "lucide-react";
import { Button } from "@/shared/ui/button";
import { ConfirmDialog } from "@/shared/ui/confirm-dialog";
import { Can } from "@/entities/permission";
import { ACTIONS, PERMISSIONS } from "@/shared/constants/permissions";
import { MANAGED_BY } from "@/shared/constants/cloudflare";
import { useEnvironmentQuery } from "@/entities/environment";
import { useCloudflareConfigQuery } from "@/entities/cloudflare-config";
import { useDeleteCloudflareConfig } from "../hooks/use-cloudflare-config";
import { useDnsRecordsQuery, useDeleteDnsRecord, useSyncDnsRecords } from "../hooks/use-dns-records";
import type { DnsRecord } from "../model/schema";
import { CloudflareBindingForm } from "./cloudflare-binding-form";
import { DnsRecordFormDialog } from "./dns-record-form-dialog";

export function CloudflareDnsPageContent({ environmentId }: { environmentId: string }) {
  const t = useTranslations("cloudflareDns");
  const { data: environment } = useEnvironmentQuery(environmentId);
  const { data: config, isLoading: configLoading } = useCloudflareConfigQuery(environmentId);
  const isBound = Boolean(config);
  const { data: records = [] } = useDnsRecordsQuery(environmentId, isBound);
  const deleteConfig = useDeleteCloudflareConfig(environmentId);
  const deleteRecord = useDeleteDnsRecord(environmentId);
  const syncMutation = useSyncDnsRecords(environmentId);

  const syncTriggered = useRef(false);
  useEffect(() => {
    if (isBound && !syncTriggered.current) {
      syncTriggered.current = true;
      syncMutation.mutate();
    }
  }, [isBound, syncMutation]);

  const [recordFormTarget, setRecordFormTarget] = useState<DnsRecord | "create" | null>(null);
  const [recordDeleteTarget, setRecordDeleteTarget] = useState<DnsRecord | null>(null);
  const [unbindConfirmOpen, setUnbindConfirmOpen] = useState(false);

  return (
    <div className="flex flex-1 flex-col gap-6 p-6">
      <div className="flex flex-col gap-1">
        <h1 className="text-xl font-bold text-foreground">{environment.name}</h1>
        <p className="text-sm text-muted-foreground">{t(`environmentTypes.${environment.type}`)}</p>
      </div>

      {configLoading && <div className="h-24 w-full animate-pulse rounded-xl bg-muted/50" />}

      {!configLoading && !isBound && <CloudflareBindingForm environmentId={environmentId} />}

      {!configLoading && config && (
        <>
          <section className="flex flex-col gap-3 rounded-xl border bg-card p-5">
            <div className="flex items-center justify-between">
              <h2 className="flex items-center gap-2 text-sm font-bold text-foreground">
                <Cloud className="size-4 text-primary" aria-hidden="true" /> {config.zoneName}
              </h2>
              <Can I={ACTIONS.MANAGE} a={PERMISSIONS.CLOUDFLARE_ACCOUNT.RESOURCE}>
                <Button variant="outline" size="sm" onClick={() => setUnbindConfirmOpen(true)}>
                  {t("binding.unbind")}
                </Button>
              </Can>
            </div>
          </section>

          <section className="flex flex-col gap-3 rounded-xl border bg-card p-5">
            <div className="flex items-center justify-between">
              <h2 className="flex items-center gap-2 text-sm font-bold text-foreground">
                <Globe className="size-4" aria-hidden="true" /> {t("records.title")}
              </h2>
              <Can I={ACTIONS.MANAGE} a={PERMISSIONS.CLOUDFLARE_ACCOUNT.RESOURCE}>
                <Button size="sm" onClick={() => setRecordFormTarget("create")}>
                  <Plus className="mr-1.5 size-3.5" aria-hidden="true" /> {t("records.addRecord")}
                </Button>
              </Can>
            </div>

            {records.length === 0 ? (
              <p className="text-sm text-muted-foreground">{t("records.empty")}</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b text-left text-xs uppercase text-muted-foreground">
                      <th className="py-2 pr-4">{t("records.type")}</th>
                      <th className="py-2 pr-4">{t("records.name")}</th>
                      <th className="py-2 pr-4">{t("records.content")}</th>
                      <th className="py-2 pr-4">{t("records.managedBy")}</th>
                      <th className="py-2" />
                    </tr>
                  </thead>
                  <tbody className="divide-y">
                    {records.map((record) => (
                      <tr key={record.id}>
                        <td className="py-2 pr-4 font-mono text-xs">{record.recordType}</td>
                        <td className="py-2 pr-4">{record.name}</td>
                        <td className="py-2 pr-4 text-muted-foreground">{record.content}</td>
                        <td className="py-2 pr-4">
                          {record.managedBy === MANAGED_BY.EXTERNAL ? (
                            <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2 py-0.5 text-[10px] font-semibold uppercase text-amber-700 dark:bg-amber-950/60 dark:text-amber-300">
                              <ExternalLink className="size-3" aria-hidden="true" /> {t("records.external")}
                            </span>
                          ) : (
                            <span className="text-xs text-muted-foreground">{t("records.system")}</span>
                          )}
                        </td>
                        <td className="py-2 text-right">
                          <Can I={ACTIONS.MANAGE} a={PERMISSIONS.CLOUDFLARE_ACCOUNT.RESOURCE}>
                            <div className="flex justify-end gap-2">
                              <button
                                type="button"
                                onClick={() => setRecordFormTarget(record)}
                                aria-label={t("records.editRecord")}
                                className="cursor-pointer text-muted-foreground hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                              >
                                <Pencil className="size-3.5" aria-hidden="true" />
                              </button>
                              <button
                                type="button"
                                onClick={() => setRecordDeleteTarget(record)}
                                aria-label={t("records.deleteRecord")}
                                className="cursor-pointer text-muted-foreground hover:text-destructive focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                              >
                                <Trash2 className="size-3.5" aria-hidden="true" />
                              </button>
                            </div>
                          </Can>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}

      {recordFormTarget !== null && (
        <DnsRecordFormDialog
          environmentId={environmentId}
          record={recordFormTarget === "create" ? null : recordFormTarget}
          onClose={() => setRecordFormTarget(null)}
        />
      )}

      <ConfirmDialog
        isOpen={recordDeleteTarget !== null}
        onClose={() => setRecordDeleteTarget(null)}
        onConfirm={() => {
          if (recordDeleteTarget) {
            deleteRecord.mutate(recordDeleteTarget.id, { onSuccess: () => setRecordDeleteTarget(null) });
          }
        }}
        title={t("records.deleteConfirm.title")}
        description={t("records.deleteConfirm.description", { name: recordDeleteTarget?.name ?? "" })}
        variant="destructive"
        isLoading={deleteRecord.isPending}
      />

      <ConfirmDialog
        isOpen={unbindConfirmOpen}
        onClose={() => setUnbindConfirmOpen(false)}
        onConfirm={() => {
          deleteConfig.mutate(undefined, { onSuccess: () => setUnbindConfirmOpen(false) });
        }}
        title={t("binding.unbindConfirm.title")}
        description={t("binding.unbindConfirm.description")}
        variant="destructive"
        isLoading={deleteConfig.isPending}
      />
    </div>
  );
}
