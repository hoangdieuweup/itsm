"use client";

import { useTranslations } from "next-intl";
import Image from "next/image";
import { Monitor, ShieldAlert, TicketCheck } from "lucide-react";

import { m } from "@/shared/lib/motion";

export function BrandPanel() {
  const t = useTranslations("auth.brand");

  return (
    <div className="relative hidden flex-col justify-between overflow-hidden text-white lg:flex lg:w-[48%]">
      {/* ── Wave background image ── */}
      <Image
        src="/images/auth-wave-bg.jpg"
        alt=""
        fill
        priority
        className="object-cover"
        sizes="48vw"
      />

      {/* ── Content overlay ── */}
      <div className="relative z-10 flex flex-1 flex-col justify-between p-10 xl:p-14">
        {/* ── Logo ── */}
        <m.div
          initial={{ opacity: 0, y: -12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4, ease: "easeOut" }}
          className="flex items-center gap-3"
        >
          <div className="flex size-9 items-center justify-center rounded-lg bg-white/20 backdrop-blur-sm">
            <span className="text-lg font-extrabold leading-none">W</span>
          </div>
          <div className="flex items-baseline gap-2">
            <span className="text-xl font-bold tracking-wide">WEUP</span>
            <span className="rounded bg-white/20 px-1.5 py-0.5 text-[10px] font-bold tracking-widest">
              ITSM
            </span>
          </div>
        </m.div>

        {/* ── Tagline + description + features ── */}
        <m.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.1, ease: "easeOut" }}
          className="flex flex-col gap-8"
        >
          <div className="space-y-4">
            <h2 className="text-4xl leading-[1.15] font-extrabold text-balance whitespace-pre-line xl:text-[2.75rem]">
              {t("tagline")}
            </h2>
            <p className="max-w-md text-[15px] leading-relaxed text-blue-100">
              {t("description")}
            </p>
          </div>

          <ul className="flex flex-col gap-3">
            {FEATURE_ENTRIES.map(({ key, Icon }, i) => (
              <m.li
                key={key}
                initial={{ opacity: 0, x: -24 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{
                  duration: 0.35,
                  delay: 0.3 + i * 0.1,
                  ease: "easeOut",
                }}
                className="inline-flex w-fit items-center gap-3 rounded-xl border border-white/15 bg-white/10 py-2.5 pr-5 pl-3 text-sm font-medium backdrop-blur-sm transition-all duration-200 hover:bg-white/[0.18] hover:border-white/25"
              >
                <span className="flex size-8 items-center justify-center rounded-lg bg-white/20">
                  <Icon className="size-4" aria-hidden />
                </span>
                {t(`features.${key}`)}
              </m.li>
            ))}
          </ul>
        </m.div>

        {/* ── Bottom accent ── */}
        <m.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.4, delay: 0.6 }}
          className="flex items-center gap-2"
          role="presentation"
          aria-hidden
        >
          <span className="h-1 w-8 rounded-full bg-white/60" />
          <span className="h-1 w-2 rounded-full bg-white/25" />
          <span className="h-1 w-2 rounded-full bg-white/25" />
        </m.div>
      </div>
    </div>
  );
}

const FEATURE_ENTRIES = [
  { key: "incidentManagement", Icon: ShieldAlert },
  { key: "requestTracking", Icon: TicketCheck },
  { key: "assetManagement", Icon: Monitor },
] as const;
