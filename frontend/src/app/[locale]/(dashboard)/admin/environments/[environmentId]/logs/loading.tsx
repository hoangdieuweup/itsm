import { Skeleton } from "@/shared/ui/skeleton";

export default function AdminEnvironmentLogsLoading() {
  return (
    <div className="p-6 space-y-6">
      <Skeleton className="h-6 w-48 mb-4" />
      <Skeleton className="h-24 w-full" />
      <Skeleton className="h-40 w-full" />
    </div>
  );
}
