// share of the hue in a cell: 8% at 0 up to 84% at 100, where white numbers still clear 4.5:1 (WCAG AA)
const share = (v: number) => (8 + 0.76 * v) / 100;

/**
 * A table whose cells carry a sequential fill (one hue, surface -> bright as the value grows) and the number itself,
 * so the colour never has to be read alone. Values are percentages (0-100).
 */
export function Heatmap({ rows, cols, value, rowLabel, colLabel, caption, highlightRow }: {
  rows: string[];
  cols: string[];
  value: (r: string, c: string) => number | undefined;
  rowLabel: (r: string) => React.ReactNode;
  colLabel: (c: string) => React.ReactNode;
  caption: string;
  highlightRow?: string;
}) {
  const fill = (v: number) => `color-mix(in srgb, var(--color-seq-400) ${Math.round(100 * share(v))}%, var(--color-chart-surface))`;
  return (
    <div className="relative overflow-x-auto">
      <table className="w-full border-separate border-spacing-[2px] text-footnote">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr>
            <th className="p-1.5 text-left font-normal text-label-tertiary" />
            {cols.map((c) => <th key={c} scope="col" className="px-1.5 pb-1.5 text-center text-caption-1 font-medium text-label-secondary">{colLabel(c)}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r}>
              <th scope="row" className={`whitespace-nowrap pr-3 text-left font-normal ${r === highlightRow ? "font-semibold text-label" : "text-label-secondary"}`}>{rowLabel(r)}</th>
              {cols.map((c) => {
                const v = value(r, c);
                return (
                  <td key={c} className="h-9 min-w-[4.5rem] rounded-[6px] text-center tabular-nums"
                    style={{ background: v === undefined ? "transparent" : fill(v), color: v === undefined ? "var(--color-label)" : "#fff" }}>
                    {v === undefined ? "—" : `${Math.round(v)}%`}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
