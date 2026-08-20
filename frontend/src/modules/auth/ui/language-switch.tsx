"use client";

import { useState } from "react";

import { cn } from "@/shared/lib/utils";

const LOCALES = ["VI", "EN"] as const;
type Locale = (typeof LOCALES)[number];

/**
 * Presentational-only pill toggle. No i18n routing is wired here — this
 * project has no i18n library yet (checked `package.json` per
 * nextjs-modular-architecture's i18n rule), so this only tracks local UI
 * state until a real locale system lands.
 */
export function LanguageSwitch() {
  const [active, setActive] = useState<Locale>("VI");

  return (
    <div
      role="group"
      aria-label="Language"
      className="inline-flex items-center rounded-full bg-muted p-0.5 text-xs font-semibold"
    >
      {LOCALES.map((locale) => (
        <button
          key={locale}
          type="button"
          aria-pressed={active === locale}
          onClick={() => setActive(locale)}
          className={cn(
            "rounded-full px-2.5 py-1 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50",
            active === locale
              ? "bg-orange-700 text-white"
              : "text-muted-foreground hover:text-foreground"
          )}
        >
          {locale}
        </button>
      ))}
    </div>
  );
}
