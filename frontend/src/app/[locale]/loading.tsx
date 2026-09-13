import { DashboardSkeleton } from "@/shared/ui/page-skeletons";

export default function RootLoading() {
  return (
    <div className="flex flex-1 p-6">
      <DashboardSkeleton />
    </div>
  );
}

