import { LogViewerSkeleton } from "@/shared/ui/page-skeletons";

export default function ProjectEnvironmentLogsLoading() {
  return (
    <div className="p-6">
      <LogViewerSkeleton />
    </div>
  );
}

