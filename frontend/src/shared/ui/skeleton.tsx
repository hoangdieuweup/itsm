import { cn } from "@/shared/lib/utils";

function Skeleton({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="skeleton"
      className={cn(
        "animate-shimmer-wave rounded-xl bg-muted/80 dark:bg-muted/50 border border-border/20",
        className,
      )}
      {...props}
    />
  );
}

export { Skeleton };

