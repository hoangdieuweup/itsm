import { Caveat } from "next/font/google";
import { BarChart3, Building2, ClipboardCheck } from "lucide-react";

import { cn } from "@/shared/lib/utils";

// Scoped to this module only — the app-wide layout keeps Geist. A script
// face is used strictly for the small logo wordmark per the split-screen
// design brief ("script/cursive wordmark style").
const caveat = Caveat({
  subsets: ["latin"],
  weight: ["600"],
  variable: "--font-logo",
});

const FEATURE_PILLS = [
  { icon: ClipboardCheck, label: "Structured training" },
  { icon: BarChart3, label: "Real-time reporting" },
  { icon: Building2, label: "Department management" },
] as const;

/**
 * Left branding panel of the split-screen login layout (Concept A layout,
 * Concept B orange→red accent — see PR description for the contrast math
 * behind these exact gradient stops, computed by hand since the
 * `ui-ux-pro-max` plugin isn't available in this environment).
 */
export function BrandPanel() {
  return (
    <div
      className={cn(
        caveat.variable,
        "relative hidden flex-col justify-between overflow-hidden bg-linear-to-br from-orange-700 via-red-800 to-red-900 p-8 text-white lg:flex lg:w-[45%] lg:p-10"
      )}
    >
      {/* Decorative texture, purely visual — no semantic content */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_15%_20%,rgba(255,255,255,0.12),transparent_45%),radial-gradient(circle_at_85%_90%,rgba(255,255,255,0.1),transparent_40%)]"
      />

      <span
        className="relative text-3xl font-semibold tracking-wide"
        style={{ fontFamily: "var(--font-logo)" }}
      >
        Weup
      </span>

      <div className="relative mt-10 flex flex-col gap-6">
        <div className="space-y-3">
          <h2 className="text-3xl leading-tight font-bold text-balance lg:text-4xl">
            Nền tảng đào tạo
            <br />
            thế hệ mới
          </h2>
          <p className="max-w-sm text-sm leading-relaxed text-white/90">
            Quản lý đào tạo, theo dõi tiến độ và vận hành phòng ban của bạn
            trong một nền tảng duy nhất.
          </p>
        </div>

        <ul className="flex flex-col gap-2.5">
          {FEATURE_PILLS.map(({ icon: Icon, label }) => (
            <li
              key={label}
              className="inline-flex w-fit items-center gap-2 rounded-full border border-white/30 bg-white/10 py-1.5 pr-4 pl-2.5 text-sm font-medium backdrop-blur-sm"
            >
              <span className="flex size-5 items-center justify-center rounded-full bg-white/20">
                <Icon className="size-3" aria-hidden />
              </span>
              {label}
            </li>
          ))}
        </ul>
      </div>

      <div
        className="relative flex items-center gap-1.5"
        role="presentation"
        aria-hidden
      >
        <span className="h-1.5 w-6 rounded-full bg-white" />
        <span className="h-1.5 w-1.5 rounded-full bg-white/40" />
        <span className="h-1.5 w-1.5 rounded-full bg-white/40" />
        <span className="h-1.5 w-1.5 rounded-full bg-white/40" />
      </div>
    </div>
  );
}
