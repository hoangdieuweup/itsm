"use client";

import { useQueryErrorResetBoundary } from "@tanstack/react-query";
import { Button } from "@/shared/ui/button";

export default function RootError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const { reset: resetQueries } = useQueryErrorResetBoundary();

  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-4 p-6 text-center">
      <h2 className="text-lg font-semibold">Something went wrong</h2>
      <p className="text-muted-foreground text-sm">{error.message}</p>
      <Button
        onClick={() => {
          resetQueries();
          reset();
        }}
      >
        Try again
      </Button>
    </div>
  );
}
