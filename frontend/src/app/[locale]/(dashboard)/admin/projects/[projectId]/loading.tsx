import { Skeleton } from "@/shared/ui/skeleton";

export default function AdminProjectDetailLoading() {
  return (
    <div className="flex flex-1 flex-col gap-6">
      <Skeleton className="h-8 w-64" />
      <div className="rounded-xl border bg-card p-5">
        <Skeleton className="h-24 w-full" />
      </div>
      <div className="rounded-xl border bg-card p-5">
        <Skeleton className="h-24 w-full" />
      </div>
    </div>
  );
}
