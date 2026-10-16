/** utils.ts — display helpers shared by table + form. */

export function debounce<T extends (...args: any[]) => void>(fn: T, ms = 300): T {
  let t: ReturnType<typeof setTimeout>;
  return ((...args: any[]) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), ms);
  }) as T;
}

export function formatCell(value: any): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "object") {
    try { return JSON.stringify(value); } catch { return String(value); }
  }
  const s = String(value);
  // trim datetime to date + HH:MM
  if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(s)) return s.slice(0, 16).replace("T", " ");
  if (/^\d{4}-\d{2}-\d{2}/.test(s)) return s.slice(0, 10);
  return s.length > 60 ? s.slice(0, 57) + "…" : s;
}

/** DRF receives naive ISO strings; datetime-local gives "YYYY-MM-DDTHH:MM". */
export function toISOOrNull(local: string): string | null {
  if (!local) return null;
  return local.length === 16 ? `${local}:00Z` : local;
}

export function fromDateOrNull(date: string): string | null {
  return date || null;
}
