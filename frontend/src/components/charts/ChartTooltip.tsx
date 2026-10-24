/**
 * Chart readout: values lead (strong), labels follow (secondary); a short line key carries series identity.
 * Positioned in the chart's own coordinate box and kept inside it.
 */
export interface TipRow {
  label: string;
  value: string;
  color?: string;
}

export function ChartTooltip({ x, y, width, title, rows }: { x: number; y: number; width: number; title?: string; rows: TipRow[] }) {
  const left = Math.min(Math.max(8, x + 12), Math.max(8, width - 200));
  return (
    <div role="tooltip" className="pointer-events-none absolute z-20 min-w-[9rem] max-w-[14rem] rounded-[0.7rem] bg-[#232326]/95 px-3 py-2 shadow-[0_12px_32px_rgb(0_0_0/0.5),inset_0_0.5px_0_rgb(255_255_255/0.12)] backdrop-blur-md"
      style={{ left, top: Math.max(4, y - 8) }}>
      {title && <p className="mb-1 text-caption-2 text-label-tertiary">{title}</p>}
      {rows.map((r) => (
        <div key={r.label} className="flex items-center gap-2 py-px">
          {r.color && <span className="h-[2px] w-2.5 shrink-0 rounded-full" style={{ background: r.color }} aria-hidden />}
          <span className="text-footnote font-semibold tabular-nums">{r.value}</span>
          <span className="truncate text-caption-1 text-label-secondary">{r.label}</span>
        </div>
      ))}
    </div>
  );
}
