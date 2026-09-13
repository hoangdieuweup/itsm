"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import {
  ShieldCheck,
  ShieldAlert,
  Eye,
  EyeOff,
  UserPlus,
  Trash2,
  Copy,
  Check,
  Zap,
  Users,
  Cable,
  Globe,
} from "lucide-react";
import { IconCloudflare } from "@/shared/ui/icons";
import { Button } from "@/shared/ui/button";
import { Skeleton } from "@/shared/ui/skeleton";
import { ConfirmDialog } from "@/shared/ui/confirm-dialog";
import { Can } from "@/entities/permission";
import { ACTIONS, PERMISSIONS } from "@/shared/constants/permissions";
import { useApiErrorMessage } from "@/shared/lib/handle-api-error";
import { useCloudflareAccountQuery } from "@/entities/cloudflare-account";
import { Avatar, AvatarFallback } from "@/shared/ui/avatar";
import { ACCESS_LEVEL, type AccessLevel, type CloudflareAccountManager } from "../api/fetchers";
import { useTestCloudflareAccountConnection } from "../hooks/use-test-cloudflare-account-connection";
import { useRevealCloudflareAccountToken } from "../hooks/use-reveal-cloudflare-account-token";
import { useCloudflareAccountManagersQuery } from "../hooks/use-cloudflare-account-managers";
import { useRemoveCloudflareAccountManager } from "../hooks/use-remove-cloudflare-account-manager";
import { useUpdateCloudflareAccountManager } from "../hooks/use-update-cloudflare-account-manager";
import { CloudflareAccountManagerFormDialog } from "./cloudflare-account-manager-form-dialog";
import { AccountTunnelsTab } from "./account-tunnels-tab";
import { AccountDnsTab } from "./account-dns-tab";
import { m, type Variants } from "@/shared/lib/motion";

interface CloudflareAccountDetailViewProps {
  accountId: string;
}

function getInitials(name?: string | null): string {
  if (!name) return "U";
  return (
    name
      .trim()
      .split(/\s+/)
      .map((p) => p[0] || "")
      .join("")
      .slice(0, 2)
      .toUpperCase() || "U"
  );
}

function ManagerAccessLevelControl({
  manager,
  onChange,
  disabled,
}: {
  manager: CloudflareAccountManager;
  onChange: (accessLevel: AccessLevel) => void;
  disabled: boolean;
}) {
  const t = useTranslations("cloudflareAccounts");

  const getLevelBadgeStyle = (level: string) => {
    switch (level.toLowerCase()) {
      case "owner":
        return "border-amber-500/40 bg-amber-500/15 text-amber-700 dark:text-amber-300";
      case "admin":
        return "border-blue-500/40 bg-blue-500/15 text-blue-700 dark:text-blue-300";
      default:
        return "border-border/70 bg-muted/60 text-foreground";
    }
  };

  return (
    <Can
      I={ACTIONS.MANAGE}
      a={PERMISSIONS.CLOUDFLARE_MANAGER.RESOURCE}
      fallback={
        <span
          className={`inline-flex items-center rounded-lg border px-2.5 py-1 text-[11px] font-bold uppercase tracking-wider ${getLevelBadgeStyle(
            manager.accessLevel
          )}`}
        >
          {t(`managers.levels.${manager.accessLevel}`)}
        </span>
      }
    >
      <select
        value={manager.accessLevel}
        onChange={(event) => onChange(event.target.value as AccessLevel)}
        disabled={disabled}
        aria-label={t("managers.accessLevel")}
        className="h-8 rounded-xl border border-border/70 bg-background/90 px-2.5 font-mono text-xs font-bold uppercase tracking-wider text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary shadow-2xs disabled:cursor-not-allowed disabled:opacity-50 cursor-pointer"
      >
        {Object.values(ACCESS_LEVEL).map((level) => (
          <option key={level} value={level}>
            {t(`managers.levels.${level}`)}
          </option>
        ))}
      </select>
    </Can>
  );
}

const containerVariants: Variants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.08,
    },
  },
};

const itemVariants: Variants = {
  hidden: { opacity: 0, y: 16 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.35 },
  },
};

/* ── Tab constants ── */
const TABS = ["tunnels", "dns", "managers"] as const;
type TabKey = (typeof TABS)[number];

const TAB_ICONS: Record<TabKey, React.ReactNode> = {
  tunnels: <Cable className="size-4" />,
  dns: <Globe className="size-4" />,
  managers: <Users className="size-4" />,
};

/**
 * Hero banner. Owns the copy/reveal interaction state, which nothing outside
 * this banner reads — keeping it here is what keeps the parent view thin.
 */
function AccountHeroBanner({ accountId }: { accountId: string }) {
  const t = useTranslations("cloudflareAccounts");
  const getErrorMessage = useApiErrorMessage("cloudflareAccounts");
  const { data: account } = useCloudflareAccountQuery(accountId);

  const testConnection = useTestCloudflareAccountConnection();
  const revealToken = useRevealCloudflareAccountToken();

  const [revealedToken, setRevealedToken] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState(false);
  const [copiedToken, setCopiedToken] = useState(false);

  const handleCopyId = () => {
    navigator.clipboard.writeText(account.cfAccountId);
    setCopiedId(true);
    setTimeout(() => setCopiedId(false), 2000);
  };

  const handleCopyToken = () => {
    if (!revealedToken) return;
    navigator.clipboard.writeText(revealedToken);
    setCopiedToken(true);
    setTimeout(() => setCopiedToken(false), 2000);
  };

  const handleToggleToken = async () => {
    if (revealedToken) {
      setRevealedToken(null);
      return;
    }
    const token = await revealToken.mutateAsync(accountId);
    setRevealedToken(token);
  };

  return (
    <m.div
      variants={itemVariants}
      className="relative overflow-hidden rounded-3xl border border-border/60 bg-gradient-to-br from-amber-500/10 via-orange-500/5 to-card/95 p-6 sm:p-8 backdrop-blur-2xl shadow-xl shadow-black/5 dark:shadow-black/20"
    >
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-6 mb-6">
        <div className="flex items-start gap-4">
          {/* Cloudflare Vivid Icon Avatar */}
          <div className="flex size-14 shrink-0 items-center justify-center rounded-2xl bg-gradient-to-br from-amber-500/10 via-orange-500/15 to-amber-600/10 p-2 shadow-lg shadow-orange-500/20 ring-4 ring-orange-500/10">
            <IconCloudflare className="size-9 rounded-xl shadow-xs" />
          </div>

          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <span className="inline-flex items-center gap-1.5 rounded-full border border-orange-500/30 bg-orange-500/15 px-3 py-0.5 text-xs font-bold text-orange-600 dark:text-orange-400">
                <Zap className="size-3.5" />
                {t("edgeZone")}
              </span>
              <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-500/30 bg-emerald-500/15 px-2.5 py-0.5 text-xs font-semibold text-emerald-600 dark:text-emerald-400">
                <span className="relative flex size-2">
                  <span className="absolute inline-flex size-full animate-ping rounded-full bg-emerald-400 opacity-75" />
                  <span className="relative inline-flex size-2 rounded-full bg-emerald-500" />
                </span>
                {t("activeStatus")}
              </span>
            </div>

            <h1 className="text-2xl font-extrabold tracking-tight text-foreground sm:text-3xl">
              {account.label}
            </h1>

            {/* Copyable Account ID Pill */}
            <div className="flex items-center gap-2 pt-0.5">
              <span className="text-xs font-medium text-muted-foreground">
                {t("accountIdLabel")}:
              </span>
              <button
                type="button"
                onClick={handleCopyId}
                className="group flex items-center gap-1.5 rounded-xl border border-border/70 bg-muted/60 px-2.5 py-1 font-mono text-xs font-semibold text-foreground transition-colors hover:border-primary/40 hover:bg-muted cursor-pointer shadow-2xs"
                title="Click to copy Account ID"
              >
                <span>{account.cfAccountId}</span>
                {copiedId ? (
                  <Check className="size-3.5 text-emerald-500" />
                ) : (
                  <Copy className="size-3.5 text-muted-foreground group-hover:text-foreground" />
                )}
              </button>
            </div>
          </div>
        </div>

        {/* Action CTAs */}
        <div className="flex flex-wrap items-center gap-3">
          <Can I={ACTIONS.TEST_CONNECTION} a={PERMISSIONS.CLOUDFLARE_ACCOUNT.RESOURCE}>
            <Button
              variant="outline"
              size="sm"
              onClick={() => testConnection.mutate(accountId)}
              disabled={testConnection.isPending}
              className="gap-2 rounded-xl border-border/70 bg-card/80 font-semibold shadow-2xs hover:border-emerald-500/40 hover:bg-emerald-500/10 hover:text-emerald-600"
            >
              <ShieldCheck className="size-4 text-emerald-500" aria-hidden="true" />
              {testConnection.isPending ? t("actions.testingApi") : t("actions.testConnection")}
            </Button>
          </Can>

          <Can I={ACTIONS.REVEAL_TOKEN} a={PERMISSIONS.CLOUDFLARE_ACCOUNT.RESOURCE}>
            <Button
              variant="outline"
              size="sm"
              onClick={handleToggleToken}
              disabled={revealToken.isPending}
              aria-pressed={Boolean(revealedToken)}
              className={`gap-2 rounded-xl font-semibold shadow-2xs ${
                revealedToken
                  ? "border-amber-500/50 bg-amber-500/15 text-amber-700 dark:text-amber-300"
                  : "border-border/70 bg-card/80 hover:border-primary/40"
              }`}
            >
              {revealedToken ? (
                <EyeOff className="size-4 text-amber-500" aria-hidden="true" />
              ) : (
                <Eye className="size-4 text-muted-foreground" aria-hidden="true" />
              )}
              {revealedToken ? t("actions.hideToken") : t("actions.revealToken")}
            </Button>
          </Can>
        </div>
      </div>

      {/* Status Alerts */}
      {testConnection.isSuccess && (
        <div className="flex items-center gap-2 rounded-2xl border border-emerald-500/30 bg-emerald-500/10 p-3.5 text-xs font-semibold text-emerald-600 dark:text-emerald-400 backdrop-blur-md shadow-2xs">
          <ShieldCheck className="size-4.5" aria-hidden="true" />
          <span>{t("actions.testConnectionSuccess")}</span>
        </div>
      )}
      {testConnection.isError && (
        <div role="alert" className="flex items-center gap-2 rounded-2xl border border-destructive/30 bg-destructive/10 p-3.5 text-xs font-semibold text-destructive backdrop-blur-md shadow-2xs">
          <ShieldAlert className="size-4.5" aria-hidden="true" />
          <span>{getErrorMessage(testConnection.error)}</span>
        </div>
      )}

      {/* Revealed Token Glass Box */}
      {revealedToken && (
        <div
          role="status"
          className="mt-4 flex items-center justify-between gap-3 rounded-2xl border border-amber-500/40 bg-amber-500/10 p-4 backdrop-blur-md shadow-lg shadow-amber-500/5"
        >
          <div className="flex items-center gap-2.5 overflow-hidden">
            <div className="flex size-7 shrink-0 items-center justify-center rounded-lg bg-amber-500/20 text-amber-700 dark:text-amber-300">
              <Zap className="size-4" />
            </div>
            <code className="text-xs font-mono font-bold break-all text-amber-800 dark:text-amber-200">
              {revealedToken}
            </code>
          </div>
          <Button
            variant="ghost"
            size="sm"
            onClick={handleCopyToken}
            className="size-8 shrink-0 p-0 text-amber-700 hover:bg-amber-500/20 dark:text-amber-300 cursor-pointer rounded-xl"
            aria-label={t("actions.copyToken")}
            title="Copy API Token"
          >
            {copiedToken ? <Check className="size-4 text-emerald-500" /> : <Copy className="size-4" />}
          </Button>
        </div>
      )}
    </m.div>
  );
}

function AccountTabNav({
  activeTab,
  onChange,
}: {
  activeTab: TabKey;
  onChange: (tab: TabKey) => void;
}) {
  const t = useTranslations("cloudflareAccounts");

  return (
    <div className="flex gap-1 rounded-2xl border border-border/50 bg-card/60 p-1 backdrop-blur-md">
      {TABS.map((tab) => (
        <button
          key={tab}
          type="button"
          onClick={() => onChange(tab)}
          className={`flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-semibold transition-all cursor-pointer ${
            activeTab === tab
              ? "bg-primary/10 text-primary shadow-sm border border-primary/20"
              : "text-muted-foreground hover:text-foreground hover:bg-muted/60 border border-transparent"
          }`}
        >
          {TAB_ICONS[tab]}
          {t(`tabs.${tab}`)}
        </button>
      ))}
    </div>
  );
}

function ManagerCard({
  manager,
  disabled,
  onChangeAccessLevel,
  onRemove,
}: {
  manager: CloudflareAccountManager;
  disabled: boolean;
  onChangeAccessLevel: (accessLevel: AccessLevel) => void;
  onRemove: () => void;
}) {
  const t = useTranslations("cloudflareAccounts");

  return (
    <div className="flex items-center justify-between rounded-2xl border border-border/60 bg-card/80 p-4 backdrop-blur-md transition-all hover:border-primary/40 hover:shadow-md shadow-2xs">
      <div className="flex items-center gap-3 overflow-hidden">
        <Avatar className="size-10 shrink-0 border border-border/80 shadow-2xs">
          <AvatarFallback className="bg-gradient-to-br from-blue-500/20 to-indigo-500/20 text-xs font-extrabold text-blue-600 dark:text-blue-400">
            {getInitials(manager.name)}
          </AvatarFallback>
        </Avatar>

        <div className="overflow-hidden space-y-0.5">
          <p className="font-bold text-sm text-foreground truncate">{manager.name}</p>
          <p className="font-mono text-xs text-muted-foreground truncate">{manager.email}</p>
        </div>
      </div>

      <div className="flex items-center gap-2 shrink-0 ml-2">
        <ManagerAccessLevelControl
          manager={manager}
          disabled={disabled}
          onChange={onChangeAccessLevel}
        />
        <Can I={ACTIONS.MANAGE} a={PERMISSIONS.CLOUDFLARE_MANAGER.RESOURCE}>
          <Button
            variant="ghost"
            size="sm"
            onClick={onRemove}
            className="size-8 p-0 rounded-xl text-rose-600 hover:bg-rose-500/10 hover:text-rose-700 dark:hover:bg-rose-950/50 cursor-pointer"
            aria-label={t("managers.removeConfirm.title")}
            title="Remove manager"
          >
            <Trash2 className="size-3.5" aria-hidden="true" />
          </Button>
        </Can>
      </div>
    </div>
  );
}

function ManagersTabPanel({
  accountId,
  onAssign,
  onRemove,
}: {
  accountId: string;
  onAssign: () => void;
  onRemove: (userId: string) => void;
}) {
  const t = useTranslations("cloudflareAccounts");
  const getErrorMessage = useApiErrorMessage("cloudflareAccounts");
  const { data: managers = [], isLoading } = useCloudflareAccountManagersQuery(accountId);
  const updateManager = useUpdateCloudflareAccountManager(accountId);

  return (
    <section className="rounded-3xl border border-border/50 bg-card/75 p-6 backdrop-blur-xl shadow-lg shadow-black/5 dark:shadow-black/20">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-2.5">
          <div className="flex size-8 items-center justify-center rounded-xl bg-blue-500/10 text-blue-600 dark:text-blue-400">
            <Users className="size-4" aria-hidden="true" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-bold uppercase tracking-wider text-foreground">
                {t("managers.title")}
              </h2>
              <span className="inline-flex items-center rounded-full border border-blue-500/30 bg-blue-500/15 px-2 py-0.5 font-mono text-[11px] font-bold text-blue-600 dark:text-blue-400">
                {managers.length}
              </span>
            </div>
          </div>
        </div>

        <Can I={ACTIONS.MANAGE} a={PERMISSIONS.CLOUDFLARE_MANAGER.RESOURCE}>
          <Button
            size="sm"
            onClick={onAssign}
            className="gap-2 bg-gradient-to-r from-blue-600 to-indigo-600 font-semibold text-white shadow-xs hover:from-blue-700 hover:to-indigo-700 rounded-xl"
          >
            <UserPlus className="size-4" aria-hidden="true" />
            {t("managers.assign")}
          </Button>
        </Can>
      </div>

      {updateManager.isError && (
        <p role="alert" className="mb-4 flex items-center gap-2 rounded-2xl border border-destructive/30 bg-destructive/10 p-3.5 text-xs text-destructive">
          <ShieldAlert className="size-4" aria-hidden="true" />
          {getErrorMessage(updateManager.error)}
        </p>
      )}

      {isLoading ? (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <Skeleton className="h-16 w-full rounded-2xl" />
          <Skeleton className="h-16 w-full rounded-2xl" />
        </div>
      ) : managers.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-border/60 bg-muted/20 py-10 text-center">
          <div className="flex size-10 items-center justify-center rounded-xl bg-muted/60 text-muted-foreground mb-2">
            <Users className="size-5" aria-hidden="true" />
          </div>
          <p className="text-sm font-medium text-muted-foreground">{t("managers.empty")}</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {managers.map((manager) => (
            <ManagerCard
              key={manager.userId}
              manager={manager}
              disabled={updateManager.isPending}
              onChangeAccessLevel={(accessLevel) =>
                updateManager.mutate({ userId: manager.userId, accessLevel })
              }
              onRemove={() => onRemove(manager.userId)}
            />
          ))}
        </div>
      )}
    </section>
  );
}

export function CloudflareAccountDetailView({ accountId }: CloudflareAccountDetailViewProps) {
  const t = useTranslations("cloudflareAccounts");
  const removeManager = useRemoveCloudflareAccountManager(accountId);

  const [assignOpen, setAssignOpen] = useState(false);
  const [removeTarget, setRemoveTarget] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<TabKey>("tunnels");

  return (
    <m.div
      variants={containerVariants}
      initial="hidden"
      animate="visible"
      className="flex flex-1 flex-col gap-8 pb-10"
    >
      {/* 1. Ultra-Premium Hero Edge Zone Banner */}
      <AccountHeroBanner accountId={accountId} />

      {/* 2. Tab Navigation */}
      <m.div variants={itemVariants}>
        <AccountTabNav activeTab={activeTab} onChange={setActiveTab} />
      </m.div>

      {/* 3. Tab Content */}
      <m.div variants={itemVariants}>
        {activeTab === "tunnels" && <AccountTunnelsTab accountId={accountId} />}
        {activeTab === "dns" && <AccountDnsTab accountId={accountId} />}
        {activeTab === "managers" && (
          <ManagersTabPanel
            accountId={accountId}
            onAssign={() => setAssignOpen(true)}
            onRemove={setRemoveTarget}
          />
        )}
      </m.div>

      {assignOpen && (
        <CloudflareAccountManagerFormDialog accountId={accountId} onClose={() => setAssignOpen(false)} />
      )}

      {removeTarget !== null && (
        <ConfirmDialog
          isOpen
          onClose={() => setRemoveTarget(null)}
          onConfirm={async () => {
            await removeManager.mutateAsync(removeTarget);
            setRemoveTarget(null);
          }}
          title={t("managers.removeConfirm.title")}
          description={t("managers.removeConfirm.description")}
          variant="destructive"
          isLoading={removeManager.isPending}
        />
      )}
    </m.div>
  );
}
