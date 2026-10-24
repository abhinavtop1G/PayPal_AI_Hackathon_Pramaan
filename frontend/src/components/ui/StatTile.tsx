import type { LucideIcon } from "lucide-react";

/**
 * A figure with its label: label (sentence case) · value (semibold, proportional figures) · optional detail line.
 * `accent` tints only the icon badge; the number stays in label ink.
 */
export function StatTile({
  label,
  value,
  detail,
  icon: Icon,
  accent = "var(--color-sys-blue)",
  className = "",
}: {
  label: string;
  value: React.ReactNode;
  detail?: React.ReactNode;
  icon?: LucideIcon;
  accent?: string;
  className?: string;
}) {
  return (
    <div className={`material-regular panel-sheen squircle relative overflow-hidden rounded-[var(--radius-card)] p-4 ${className}`}>
      <div className="flex items-center gap-2">
        {Icon && (
          <span className="flex size-6 items-center justify-center rounded-[0.45rem]"
            style={{ background: `color-mix(in srgb, ${accent} 16%, transparent)`, color: accent }}>
            <Icon className="size-3.5" aria-hidden />
          </span>
        )}
        <p className="text-footnote text-label-secondary">{label}</p>
      </div>
      <p className="mt-2 text-title-1 font-semibold tracking-[-0.025em]">{value}</p>
      {detail && <p className="mt-0.5 text-caption-1 text-label-tertiary">{detail}</p>}
    </div>
  );
}
