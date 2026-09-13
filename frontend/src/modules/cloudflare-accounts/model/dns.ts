export const DNS_TYPES = ["A", "AAAA", "CNAME", "MX", "TXT", "NS", "SRV", "CAA", "HTTPS"] as const;

export type DnsType = (typeof DNS_TYPES)[number];

/** Badge classes per record type. Text uses the 700/300 shades so the 11px
 *  labels keep 4.5:1 contrast on their tinted background in both themes. */
export const DNS_TYPE_COLORS: Record<DnsType, string> = {
  A: "border-emerald-500/30 bg-emerald-500/15 text-emerald-700 dark:text-emerald-300",
  AAAA: "border-teal-500/30 bg-teal-500/15 text-teal-700 dark:text-teal-300",
  CNAME: "border-blue-500/30 bg-blue-500/15 text-blue-700 dark:text-blue-300",
  MX: "border-purple-500/30 bg-purple-500/15 text-purple-700 dark:text-purple-300",
  TXT: "border-gray-500/30 bg-gray-500/15 text-gray-700 dark:text-gray-300",
  NS: "border-amber-500/30 bg-amber-500/15 text-amber-700 dark:text-amber-300",
  SRV: "border-pink-500/30 bg-pink-500/15 text-pink-700 dark:text-pink-300",
  CAA: "border-red-500/30 bg-red-500/15 text-red-700 dark:text-red-300",
  HTTPS: "border-lime-500/30 bg-lime-500/15 text-lime-700 dark:text-lime-300",
};

export const isDnsType = (value: string): value is DnsType =>
  (DNS_TYPES as readonly string[]).includes(value);

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
