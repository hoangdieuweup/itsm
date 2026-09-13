"use client";

import { useQueryErrorResetBoundary } from "@tanstack/react-query";
import { ErrorView } from "@/shared/ui/error-view";

export default function RootError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const { reset: resetQueries } = useQueryErrorResetBoundary();

  const handleRetry = () => {
    resetQueries();
    reset();
  };

  return (
    <div className="flex flex-1 items-center justify-center p-4 sm:p-6">
      <ErrorView
        status="500"
        error={error}
        onRetry={handleRetry}
        showBack
        showDashboard
      />
    </div>
  );
}

