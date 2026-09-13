import Link from "next/link";
import { Compass, LayoutDashboard } from "lucide-react";

export default function GlobalNotFound() {
  return (
    <div className="relative flex min-h-screen w-full flex-1 items-center justify-center p-6 bg-background text-foreground overflow-hidden">
      {/* Glow */}
      <div className="pointer-events-none absolute size-96 rounded-full bg-indigo-500/10 blur-3xl opacity-70" />

      <div className="relative z-10 w-full max-w-lg rounded-3xl border border-border/70 bg-card/75 p-8 shadow-2xl backdrop-blur-2xl text-center space-y-6">
        <div className="flex justify-center">
          <div className="flex size-20 items-center justify-center rounded-3xl border border-indigo-500/30 bg-indigo-500/10 text-indigo-500 shadow-xl shadow-indigo-500/10">
            <Compass className="size-10 stroke-[1.75]" />
          </div>
        </div>

        <div className="space-y-2">
          <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full border border-border text-xs font-mono font-semibold tracking-wide uppercase">
            404 NOT FOUND
          </div>
          <h1 className="text-3xl font-bold tracking-tight">Page Not Found</h1>
          <p className="text-sm text-muted-foreground max-w-sm mx-auto">
            The page or resource you are looking for does not exist or has been moved.
          </p>
        </div>

        <div className="pt-2 flex justify-center">
          <Link
            href="/"
            className="inline-flex items-center gap-2 rounded-xl bg-primary px-5 py-2.5 text-sm font-medium text-primary-foreground shadow-md hover:bg-primary/90 transition-colors"
          >
            <LayoutDashboard className="size-4" />
            Return to Homepage
          </Link>
        </div>
      </div>
    </div>
  );
}
