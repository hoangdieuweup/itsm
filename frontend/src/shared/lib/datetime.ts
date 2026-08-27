/**
 * Shared datetime utilities.
 *
 * All display-facing helpers render in the browser's local timezone by default.
 * The `toDatetimeLocal` helper is for populating `<input type="datetime-local">`.
 */

const pad = (n: number) => String(n).padStart(2, "0");

// ─── Display Formatters ────────────────────────────────────────────

/** Full datetime: "26/08/2026, 14:30:00" */
export function formatDatetime(value: string | Date): string {
  const date = typeof value === "string" ? new Date(value) : value;
  return date.toLocaleString(undefined, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

/** Date only: "26/08/2026" */
export function formatDate(value: string | Date): string {
  const date = typeof value === "string" ? new Date(value) : value;
  return date.toLocaleDateString(undefined, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
}

// ─── Input Helpers ─────────────────────────────────────────────────

/**
 * Convert a Date to the `YYYY-MM-DDTHH:mm` format used by
 * `<input type="datetime-local">` (always local timezone).
 */
export function toDatetimeLocal(date: Date): string {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
}

/**
 * Produce a { start, end } pair of `datetime-local` strings
 * spanning the last `rangeMinutes` minutes up to now.
 */
export function defaultRange(rangeMinutes: number): { start: string; end: string } {
  const end = new Date();
  const start = new Date(end.getTime() - rangeMinutes * 60_000);
  return { start: toDatetimeLocal(start), end: toDatetimeLocal(end) };
}
