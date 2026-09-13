import { Skeleton } from "./skeleton";

export function PageHeaderSkeleton({
  hasAction = true,
  actionWidth = "w-32",
}: {
  hasAction?: boolean;
  actionWidth?: string;
}) {
  return (
    <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
      <div className="space-y-2">
        <div className="flex items-center gap-3">
          <Skeleton className="h-8 w-44 sm:w-56" />
          <Skeleton className="h-5 w-16 rounded-full" />
        </div>
        <Skeleton className="h-4 w-64 sm:w-80" />
      </div>
      {hasAction && (
        <div className="flex items-center gap-2">
          <Skeleton className={`h-9 ${actionWidth} rounded-xl`} />
        </div>
      )}
    </div>
  );
}

export function TablePageSkeleton({
  rows = 5,
  hasFilters = true,
}: {
  rows?: number;
  hasFilters?: boolean;
}) {
  return (
    <div className="flex flex-1 flex-col gap-6">
      <PageHeaderSkeleton />

      {hasFilters && (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <Skeleton className="h-10 w-full max-w-sm rounded-xl" />
          <div className="flex items-center gap-2">
            <Skeleton className="h-10 w-28 rounded-xl" />
            <Skeleton className="h-10 w-24 rounded-xl" />
          </div>
        </div>
      )}

      <div className="overflow-hidden rounded-2xl border border-border/70 bg-card/60 p-4 shadow-sm backdrop-blur-md sm:p-6">
        <div className="space-y-4">
          <div className="flex items-center justify-between border-b border-border/50 pb-3">
            <Skeleton className="h-4 w-28" />
            <Skeleton className="h-4 w-36 hidden sm:block" />
            <Skeleton className="h-4 w-24 hidden md:block" />
            <Skeleton className="h-4 w-16" />
          </div>

          {Array.from({ length: rows }).map((_, i) => (
            <div
              key={i}
              className="flex items-center justify-between py-2.5 transition-colors border-b border-border/30 last:border-0"
            >
              <div className="flex items-center gap-3">
                <Skeleton className="size-9 rounded-xl shrink-0" />
                <div className="space-y-1.5">
                  <Skeleton className="h-4 w-32 sm:w-44" />
                  <Skeleton className="h-3 w-48 sm:w-60" />
                </div>
              </div>
              <Skeleton className="h-6 w-20 rounded-full hidden sm:block" />
              <Skeleton className="h-5 w-28 hidden md:block" />
              <div className="flex items-center gap-1.5">
                <Skeleton className="size-8 rounded-lg" />
                <Skeleton className="size-8 rounded-lg" />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export function CardsPageSkeleton({
  cards = 4,
}: {
  cards?: number;
}) {
  return (
    <div className="flex flex-1 flex-col gap-6">
      <PageHeaderSkeleton />

      <div className="flex flex-wrap items-center justify-between gap-3">
        <Skeleton className="h-10 w-full max-w-sm rounded-xl" />
        <Skeleton className="h-10 w-32 rounded-xl" />
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: cards }).map((_, i) => (
          <div
            key={i}
            className="flex flex-col justify-between rounded-2xl border border-border/60 bg-card/60 p-5 shadow-sm backdrop-blur-md"
          >
            <div className="space-y-3">
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-3">
                  <Skeleton className="size-10 rounded-xl shrink-0" />
                  <div className="space-y-1.5">
                    <Skeleton className="h-4 w-28" />
                    <Skeleton className="h-3 w-40" />
                  </div>
                </div>
                <Skeleton className="size-7 rounded-lg" />
              </div>
              <Skeleton className="h-12 w-full rounded-xl" />
            </div>

            <div className="mt-5 flex items-center justify-between border-t border-border/40 pt-3">
              <Skeleton className="h-5 w-20 rounded-full" />
              <div className="flex gap-1.5">
                <Skeleton className="size-7 rounded-lg" />
                <Skeleton className="size-7 rounded-lg" />
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function DetailPageSkeleton() {
  return (
    <div className="flex flex-1 flex-col gap-6">
      {/* Breadcrumb skeleton */}
      <div className="flex items-center gap-2">
        <Skeleton className="h-4 w-16" />
        <span className="text-muted-foreground/40">/</span>
        <Skeleton className="h-4 w-24" />
        <span className="text-muted-foreground/40">/</span>
        <Skeleton className="h-4 w-32" />
      </div>

      {/* Hero Header */}
      <div className="flex flex-col gap-4 rounded-3xl border border-border/60 bg-card/60 p-6 backdrop-blur-md sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-4">
          <Skeleton className="size-14 rounded-2xl shrink-0" />
          <div className="space-y-2">
            <div className="flex items-center gap-2">
              <Skeleton className="h-6 w-48" />
              <Skeleton className="h-5 w-16 rounded-full" />
            </div>
            <Skeleton className="h-4 w-64 sm:w-96" />
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Skeleton className="h-9 w-24 rounded-xl" />
          <Skeleton className="h-9 w-28 rounded-xl" />
        </div>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-2 border-b border-border/50 pb-2">
        <Skeleton className="h-8 w-28 rounded-xl" />
        <Skeleton className="h-8 w-28 rounded-xl" />
        <Skeleton className="h-8 w-28 rounded-xl" />
      </div>

      {/* Content grid */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2 space-y-6">
          <div className="rounded-2xl border border-border/60 bg-card/60 p-6 backdrop-blur-md space-y-4">
            <Skeleton className="h-5 w-36" />
            <Skeleton className="h-28 w-full rounded-xl" />
            <div className="grid grid-cols-2 gap-3 pt-2">
              <Skeleton className="h-16 rounded-xl" />
              <Skeleton className="h-16 rounded-xl" />
            </div>
          </div>

          <div className="rounded-2xl border border-border/60 bg-card/60 p-6 backdrop-blur-md space-y-4">
            <div className="flex items-center justify-between">
              <Skeleton className="h-5 w-40" />
              <Skeleton className="h-8 w-24 rounded-lg" />
            </div>
            <Skeleton className="h-32 w-full rounded-xl" />
          </div>
        </div>

        <div className="space-y-6">
          <div className="rounded-2xl border border-border/60 bg-card/60 p-6 backdrop-blur-md space-y-4">
            <Skeleton className="h-5 w-28" />
            <div className="space-y-2.5">
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-5/6" />
              <Skeleton className="h-4 w-4/6" />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export function DashboardSkeleton() {
  return (
    <div className="flex flex-1 flex-col gap-6">
      {/* Hero Welcome Banner */}
      <div className="relative overflow-hidden rounded-3xl border border-primary/20 bg-linear-to-r from-primary/10 via-primary/5 to-accent/10 p-6 backdrop-blur-md sm:p-8">
        <div className="space-y-3 max-w-xl">
          <Skeleton className="h-8 w-64 sm:w-80" />
          <Skeleton className="h-4 w-full" />
          <div className="flex items-center gap-3 pt-2">
            <Skeleton className="h-7 w-32 rounded-full" />
            <Skeleton className="h-7 w-28 rounded-full" />
          </div>
        </div>
      </div>

      {/* 4 Stats Cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div
            key={i}
            className="flex flex-col justify-between rounded-2xl border border-border/60 bg-card/60 p-5 shadow-sm backdrop-blur-md"
          >
            <div className="flex items-center justify-between">
              <Skeleton className="h-4 w-24" />
              <Skeleton className="size-9 rounded-xl" />
            </div>
            <div className="mt-4 space-y-1.5">
              <Skeleton className="h-7 w-16" />
              <Skeleton className="h-3 w-32" />
            </div>
          </div>
        ))}
      </div>

      {/* 2-Column Split */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2 rounded-2xl border border-border/60 bg-card/60 p-6 backdrop-blur-md space-y-4">
          <div className="flex items-center justify-between">
            <Skeleton className="h-5 w-40" />
            <Skeleton className="h-7 w-20 rounded-lg" />
          </div>
          <Skeleton className="h-64 w-full rounded-xl" />
        </div>

        <div className="rounded-2xl border border-border/60 bg-card/60 p-6 backdrop-blur-md space-y-4">
          <Skeleton className="h-5 w-32" />
          <div className="space-y-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="flex items-center gap-3 py-1.5">
                <Skeleton className="size-8 rounded-lg shrink-0" />
                <div className="space-y-1 flex-1">
                  <Skeleton className="h-3.5 w-full" />
                  <Skeleton className="h-3 w-2/3" />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

export function LogViewerSkeleton() {
  return (
    <div className="flex flex-1 flex-col gap-4">
      {/* Query bar */}
      <div className="flex flex-col gap-3 rounded-2xl border border-border/60 bg-card/60 p-4 backdrop-blur-md sm:flex-row sm:items-center">
        <Skeleton className="h-10 flex-1 rounded-xl" />
        <div className="flex items-center gap-2">
          <Skeleton className="h-10 w-28 rounded-xl" />
          <Skeleton className="h-10 w-24 rounded-xl" />
          <Skeleton className="h-10 w-10 rounded-xl" />
        </div>
      </div>

      {/* Stream controls */}
      <div className="flex items-center justify-between px-1">
        <div className="flex items-center gap-2">
          <Skeleton className="h-6 w-24 rounded-full" />
          <Skeleton className="h-6 w-32 rounded-full" />
        </div>
        <Skeleton className="h-6 w-20 rounded-full" />
      </div>

      {/* Console log box */}
      <div className="flex-1 min-h-[420px] rounded-2xl border border-border/60 bg-card/75 p-5 font-mono shadow-sm backdrop-blur-xl space-y-3">
        {Array.from({ length: 12 }).map((_, i) => (
          <div key={i} className="flex items-center gap-3 text-xs opacity-75">
            <Skeleton className="h-3.5 w-24 shrink-0" />
            <Skeleton className="h-3.5 w-12 shrink-0" />
            <Skeleton
              className={`h-3.5 ${
                i % 3 === 0 ? "w-4/5" : i % 2 === 0 ? "w-3/5" : "w-2/3"
              }`}
            />
          </div>
        ))}
      </div>
    </div>
  );
}
