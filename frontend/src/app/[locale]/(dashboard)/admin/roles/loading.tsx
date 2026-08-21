import { Skeleton } from "@/shared/ui/skeleton";

export default function AdminRolesLoading() {
  return (
    <div className="flex flex-1 flex-col gap-6">
      <div className="flex flex-col gap-2">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-4 w-72" />
      </div>
      <div className="overflow-hidden rounded-xl border bg-card p-6">
        <div className="space-y-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="flex items-center justify-between py-2">
              <div className="flex items-center gap-3">
                <Skeleton className="size-8 rounded-lg" />
                <Skeleton className="h-4 w-28" />
              </div>
              <Skeleton className="h-6 w-20 rounded-full" />
              <Skeleton className="h-6 w-48 rounded-md" />
              <div className="flex gap-2">
                <Skeleton className="h-8 w-14 rounded-md" />
                <Skeleton className="h-8 w-14 rounded-md" />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
