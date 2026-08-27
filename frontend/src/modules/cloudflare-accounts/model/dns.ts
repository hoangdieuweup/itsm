export const DNS_TYPES = ["A", "AAAA", "CNAME", "MX", "TXT", "NS", "SRV", "CAA", "HTTPS"] as const;

export type DnsType = (typeof DNS_TYPES)[number];

export const DNS_TYPE_COLORS: Record<string, string> = {
  A: "border-emerald-500/30 bg-emerald-500/15 text-emerald-600 dark:text-emerald-400",
  AAAA: "border-teal-500/30 bg-teal-500/15 text-teal-600 dark:text-teal-400",
  CNAME: "border-blue-500/30 bg-blue-500/15 text-blue-600 dark:text-blue-400",
  MX: "border-purple-500/30 bg-purple-500/15 text-purple-600 dark:text-purple-400",
  TXT: "border-gray-500/30 bg-gray-500/15 text-gray-600 dark:text-gray-400",
  NS: "border-amber-500/30 bg-amber-500/15 text-amber-600 dark:text-amber-400",
  SRV: "border-pink-500/30 bg-pink-500/15 text-pink-600 dark:text-pink-400",
  CAA: "border-red-500/30 bg-red-500/15 text-red-600 dark:text-red-400",
};

/** Record types Cloudflare can put behind its proxy. */
const PROXYABLE_TYPES = new Set<string>(["A", "AAAA", "CNAME"]);

export const isProxyable = (recordType: string): boolean => PROXYABLE_TYPES.has(recordType);

/** Record types that carry a priority field. */
const PRIORITY_TYPES = new Set<string>(["MX", "SRV"]);

export const hasPriority = (recordType: string): boolean => PRIORITY_TYPES.has(recordType);

export function contentPlaceholderFor(recordType: string): string {
  if (recordType === "A") return "192.0.2.1";
  if (recordType === "CNAME") return "example.com";
  return "";
}
