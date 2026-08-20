"use client";

import { useLocale } from "next-intl";
import { usePathname, useRouter } from "@/shared/lib/i18n/navigation";
import { routing, type Locale } from "@/shared/lib/i18n/routing";
import { cn } from "@/shared/lib/utils";

/**
 * Pill toggle that switches the active locale via next-intl's locale-aware
 * router. Replaces the old presentational-only toggle.
 *
 * a11y (ui-ux-pro-max): role="group" with aria-label, each button uses
 * aria-pressed for toggle state, focus-visible ring for keyboard navigation.
 */
export function LanguageSwitch() {
  const locale = useLocale();
  const router = useRouter();
  const pathname = usePathname();

  function switchLocale(nextLocale: Locale) {
    router.replace(pathname, { locale: nextLocale });
  }

  return (
    <div
      role="group"
      aria-label="Language"
      className="inline-flex items-center rounded-full bg-muted p-0.5 text-xs font-semibold"
    >
      {routing.locales.map((loc) => (
        <button
          key={loc}
          type="button"
          aria-pressed={locale === loc}
          onClick={() => switchLocale(loc)}
          className={cn(
            "rounded-full px-2.5 py-1 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50",
            locale === loc
              ? "bg-orange-700 text-white"
              : "text-muted-foreground hover:text-foreground"
          )}
        >
          {loc.toUpperCase()}
        </button>
      ))}
    </div>
  );
}
