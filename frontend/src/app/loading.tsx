import { Skeleton } from "@/shared/ui/skeleton";

export default function RootLoading() {
  return (
    <div className="flex flex-1 items-center justify-center p-6">
      <Skeleton className="h-10 w-40" />
    </div>
  );
}
