import { ErrorView } from "@/shared/ui/error-view";

export default function NotFoundPage() {
  return (
    <div className="flex flex-1 items-center justify-center p-6">
      <ErrorView
        status="404"
        showBack
        showDashboard
      />
    </div>
  );
}
