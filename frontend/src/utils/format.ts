const inr = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });
const inr2 = new Intl.NumberFormat("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

/** ₹12,000 · ₹2,48,310 (Indian digit grouping). Values under ₹10 keep paise. */
export const rupees = (v: number) => `₹${Math.abs(v) < 10 && v !== 0 ? inr2.format(v) : inr.format(v)}`;

/** 0.996082 → "99.6%"; tiny values keep two decimals so 0.0025 reads as "0.25%". */
export function pct(p: number) {
  const v = p * 100;
  if (v >= 99.95 && v < 100) return "99.9%";
  if (v < 1) return `${v.toFixed(2)}%`;
  return `${v.toFixed(1)}%`;
}

/** Simulated wall-clock for a session minute: "11:05". */
export function clock(startIso: string, tsMin: number) {
  const d = new Date(new Date(startIso).getTime() + tsMin * 60_000);
  return `${d.getHours()}:${String(d.getMinutes()).padStart(2, "0")}`;
}

/** Simulated date for a session minute: "Sunday, 15 March". */
export function dateLabel(startIso: string, tsMin: number) {
  return new Intl.DateTimeFormat("en-IN", { weekday: "long", day: "numeric", month: "long" }).format(
    new Date(new Date(startIso).getTime() + tsMin * 60_000),
  );
}

/** Call duration "m:ss" (or "h:mm:ss") from session minutes. */
export function duration(min: number) {
  const s = Math.max(0, Math.round(min * 60));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const ss = String(s % 60).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${ss}` : `${m}:${ss}`;
}

/** Session-relative time: "+4.4 min", "+8.2 h", "+2.3 d" — sessions run from minutes (calls) to days (investment scams). */
export function since(min: number, sign = true) {
  const p = sign ? "+" : "";
  if (min < 120) return `${p}${min.toFixed(1)} min`;
  if (min < 48 * 60) return `${p}${(min / 60).toFixed(1)} h`;
  return `${p}${(min / 1440).toFixed(1)} d`;
}

/** Axis tick label for a session minute, in the unit that fits the whole session. */
export function tickLabel(min: number, maxMin: number) {
  if (min === 0) return "0";
  if (maxMin < 120) return `${Math.round(min)} min`;
  if (maxMin < 48 * 60) return `${Math.round(min / 60)} h`;
  return `${Math.round(min / 1440)} d`;
}

/** A round tick step for an axis spanning `max` minutes (≤ 6 ticks). */
export function niceStep(max: number) {
  const steps = [0.5, 1, 2, 5, 10, 15, 20, 30, 60, 120, 180, 240, 360, 720, 1440, 2880];
  return steps.find((s) => max / s <= 6) ?? 2880;
}
