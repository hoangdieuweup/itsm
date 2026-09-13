"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import {
  ShieldAlert,
  Compass,
  AlertTriangle,
  RotateCcw,
  ArrowLeft,
  LayoutDashboard,
  ChevronDown,
  ChevronUp,
  Terminal,
  type LucideIcon,
} from "lucide-react";
import { Link, useRouter } from "@/shared/lib/i18n/navigation";
import { cn } from "@/shared/lib/utils";
import { Button, buttonVariants } from "./button";

export type ErrorViewStatus = "403" | "404" | "500" | "error";

interface ErrorStatusConfig {
  code: string;
  defaultTitle: string;
  defaultDescription: string;
  badge: string;
  icon: LucideIcon;
  glowColor: string;
  badgeColor: string;
  iconContainer: string;
}

interface ErrorViewProps {
  status?: ErrorViewStatus;
  title?: string;
  description?: string;
  error?: Error & { digest?: string };
  onRetry?: () => void;
  showBack?: boolean;
  showDashboard?: boolean;
}

function useErrorStatusConfig(status: ErrorViewStatus, description?: string): ErrorStatusConfig {
  const tPages = useTranslations("common.errorPages");

  switch (status) {
    case "403":
      return {
        code: "403",
        defaultTitle: tPages("forbidden.title"),
        defaultDescription: description || tPages("forbidden.description"),
        badge: tPages("forbidden.badge"),
        icon: ShieldAlert,
        glowColor: "from-amber-500/20 via-orange-500/10 to-transparent",
        badgeColor: "bg-amber-500/10 border-amber-500/30 text-amber-600 dark:text-amber-400",
        iconContainer: "bg-amber-500/10 border-amber-500/30 text-amber-600 dark:text-amber-400 shadow-amber-500/10",
      };
    case "404":
      return {
        code: "404",
        defaultTitle: tPages("notFound.title"),
        defaultDescription: description || tPages("notFound.description"),
        badge: tPages("notFound.badge"),
        icon: Compass,
        glowColor: "from-indigo-500/20 via-purple-500/10 to-transparent",
        badgeColor: "bg-indigo-500/10 border-indigo-500/30 text-indigo-600 dark:text-indigo-400",
        iconContainer: "bg-indigo-500/10 border-indigo-500/30 text-indigo-600 dark:text-indigo-400 shadow-indigo-500/10",
      };
    case "error":
      return {
        code: "ERR",
        defaultTitle: tPages("appError.title"),
        defaultDescription: description || tPages("appError.description"),
        badge: tPages("appError.badge"),
        icon: AlertTriangle,
        glowColor: "from-rose-500/20 via-red-500/10 to-transparent",
        badgeColor: "bg-rose-500/10 border-rose-500/30 text-rose-600 dark:text-rose-400",
        iconContainer: "bg-rose-500/10 border-rose-500/30 text-rose-600 dark:text-rose-400 shadow-rose-500/10",
      };
    case "500":
    default:
      return {
        code: "500",
        defaultTitle: tPages("serverError.title"),
        defaultDescription: description || tPages("serverError.description"),
        badge: tPages("serverError.badge"),
        icon: AlertTriangle,
        glowColor: "from-rose-500/20 via-red-500/10 to-transparent",
        badgeColor: "bg-rose-500/10 border-rose-500/30 text-rose-600 dark:text-rose-400",
        iconContainer: "bg-rose-500/10 border-rose-500/30 text-rose-600 dark:text-rose-400 shadow-rose-500/10",
      };
  }
}

function ErrorDiagnostics({ error }: { error: Error & { digest?: string } }) {
  const tPages = useTranslations("common.errorPages.actions");
  const [isOpen, setIsOpen] = useState(false);

  const digestLabel = error.digest ? `${tPages("digest")}: ${error.digest}` : tPages("stackTrace");

  return (
    <div className="my-6 text-left">
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="flex w-full items-center justify-between rounded-xl border border-border/50 bg-muted/30 px-3.5 py-2 text-xs font-mono text-muted-foreground hover:bg-muted/50 hover:text-foreground transition-colors cursor-pointer"
      >
        <span className="flex items-center gap-2">
          <Terminal className="size-3.5" />
          <span>{tPages("diagnostics")} ({digestLabel})</span>
        </span>
        {isOpen ? <ChevronUp className="size-3.5" /> : <ChevronDown className="size-3.5" />}
      </button>

      {isOpen && (
        <div className="mt-2 rounded-xl border border-border/80 bg-zinc-950 p-3.5 font-mono text-xs text-zinc-300 shadow-inner overflow-x-auto max-h-48 whitespace-pre-wrap leading-normal">
          <div className="text-rose-400 font-semibold mb-1">{error.name}: {error.message}</div>
          {error.digest && <div className="text-zinc-500 mb-1">{tPages("digest")}: {error.digest}</div>}
          {error.stack && <div className="text-zinc-400 text-[11px] opacity-80">{error.stack}</div>}
        </div>
      )}
    </div>
  );
}

function ErrorActions({
  onRetry,
  showBack,
  showDashboard,
}: {
  onRetry?: () => void;
  showBack: boolean;
  showDashboard: boolean;
}) {
  const tPages = useTranslations("common.errorPages.actions");
  const router = useRouter();

  return (
    <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
      {onRetry && (
        <Button
          onClick={onRetry}
          variant="default"
          size="default"
          className="rounded-xl shadow-md gap-2 font-medium px-5 cursor-pointer h-10"
        >
          <RotateCcw className="size-4" />
          {tPages("tryAgain")}
        </Button>
      )}

      {showDashboard && (
        <Link
          href="/dashboard"
          className={cn(
            buttonVariants({ variant: onRetry ? "outline" : "default", size: "default" }),
            "rounded-xl gap-2 font-medium px-5 cursor-pointer h-10",
          )}
        >
          <LayoutDashboard className="size-4" />
          {tPages("backToDashboard")}
        </Link>
      )}

      {showBack && (
        <Button
          onClick={() => router.back()}
          variant="ghost"
          size="default"
          className="rounded-xl gap-1.5 text-muted-foreground hover:text-foreground cursor-pointer h-10"
        >
          <ArrowLeft className="size-4" />
          <span>{tPages("goBack")}</span>
        </Button>
      )}
    </div>
  );
}

export function ErrorView({
  status = "500",
  title,
  description,
  error,
  onRetry,
  showBack = true,
  showDashboard = true,
}: ErrorViewProps) {
  const config = useErrorStatusConfig(status, description);
  const displayTitle = title || config.defaultTitle;
  const displayDesc = description || config.defaultDescription;
  const Icon = config.icon;

  return (
    <div className="relative flex min-h-[65vh] w-full flex-1 items-center justify-center p-4 sm:p-6 overflow-hidden">
      {/* Ambient background glow */}
      <div
        className={`pointer-events-none absolute -top-24 left-1/2 -translate-x-1/2 size-96 rounded-full bg-radial ${config.glowColor} blur-3xl opacity-70 animate-[pulse-glow_6s_infinite_ease-in-out]`}
        aria-hidden="true"
      />

      {/* Main glass card */}
      <div className="relative z-10 w-full max-w-lg rounded-3xl border border-border/70 bg-card/75 p-6 shadow-2xl backdrop-blur-2xl sm:p-10 text-center">
        {/* Animated Status Icon */}
        <div className="flex justify-center mb-6">
          <div
            className={`relative flex size-20 items-center justify-center rounded-3xl border shadow-xl ${config.iconContainer} animate-[float-slow_4s_infinite_ease-in-out]`}
          >
            <Icon className="size-10 stroke-[1.75]" aria-hidden="true" />
            <div className="absolute -bottom-2.5 px-2.5 py-0.5 rounded-full border text-[10px] font-mono font-bold tracking-wider uppercase bg-card/90 shadow-xs border-border">
              {config.code}
            </div>
          </div>
        </div>

        {/* Badge & Title */}
        <div className="space-y-2 mb-4">
          <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full border text-xs font-mono font-semibold tracking-wide uppercase mb-1">
            <span className="size-1.5 rounded-full bg-current animate-pulse" />
            {config.badge}
          </div>
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-foreground">{displayTitle}</h1>
          <p className="text-sm text-muted-foreground max-w-md mx-auto leading-relaxed">{displayDesc}</p>
        </div>

        {/* Technical diagnostics */}
        {error && <ErrorDiagnostics error={error} />}

        {/* Action button bar */}
        <ErrorActions
          onRetry={onRetry}
          showBack={showBack}
          showDashboard={showDashboard}
        />
      </div>
    </div>
  );
}
