import type { LucideIcon } from "lucide-react";

/**
 * A glass console panel: optional icon badge, eyebrow label, title, optional trailing accessory, content slot.
 * `tint` colours the icon badge (a system colour variable).
 */
export function Panel({
  eyebrow,
  title,
  icon: Icon,
  tint = "var(--color-sys-blue)",
  accessory,
  className = "",
  children,
}: {
  eyebrow: string;
  title: string;
  icon?: LucideIcon;
  tint?: string;
  accessory?: React.ReactNode;
  className?: string;
  children?: React.ReactNode;
}) {
  return (
    <section className={`material-regular panel-sheen squircle flex min-h-0 min-w-0 flex-col rounded-[var(--radius-panel)] p-5 ${className}`}>
      <header className="mb-4 flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          {Icon && (
            <span
              className="squircle flex size-9 shrink-0 items-center justify-center rounded-[0.7rem]"
              style={{ background: `color-mix(in srgb, ${tint} 16%, transparent)`, color: tint }}
            >
              <Icon className="size-[1.1rem]" aria-hidden />
            </span>
          )}
          <div className="min-w-0">
            <p className="text-eyebrow text-label-tertiary">{eyebrow}</p>
            <h2 className="mt-0.5 truncate text-title-3">{title}</h2>
          </div>
        </div>
        {accessory}
      </header>
      <div className="relative min-h-0 flex-1">{children}</div>
    </section>
  );
}
