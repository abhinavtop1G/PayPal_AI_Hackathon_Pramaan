import { Signal, Wifi } from "lucide-react";

/** Safe-area insets, as padding classes for screens inside the frame. */
export const SAFE_AREA = "pt-[3.4rem] pb-8";

/**
 * Bezel-less phone mockup at its logical size, 390 × 844 pt (a current 6.1" iPhone); PhoneScaler fits it to the
 * pane. The frame is a thin titanium rim around an edge-to-edge screen; everything inside `children`
 * is laid out in that 390-wide coordinate space, between the status bar and the home indicator.
 */
export function PhoneFrame({
  children,
  overlay,
  island,
  time = "9:41",
  tone = "light",
}: {
  children: React.ReactNode;
  overlay?: React.ReactNode;
  island?: React.ReactNode;
  time?: string;
  /** status bar and home indicator colour: light glyphs on dark screens, dark glyphs on light ones */
  tone?: "light" | "dark";
}) {
  return (
    <div className="relative h-[52.75rem] w-[24.375rem] select-none" aria-label="Customer's phone">
      {/* rim: a 1px light edge over a near-black band reads as polished metal without a heavy bezel */}
      <div
        className="squircle absolute -inset-[0.6875rem] rounded-[calc(var(--radius-device)+0.6875rem)] bg-[#0b0b0c]"
        style={{
          boxShadow:
            "inset 0 0 0 1px rgb(255 255 255 / 0.10), inset 0 1px 0 rgb(255 255 255 / 0.18), 0 0 0 1px #000, 0 60px 120px -40px rgb(0 0 0 / 0.9), 0 0 80px -20px rgb(94 92 230 / 0.18)",
        }}
      />
      {/* side buttons */}
      <span aria-hidden className="absolute -left-[0.8rem] top-[18%] h-8 w-[3px] rounded-l bg-[#1a1a1c]" />
      <span aria-hidden className="absolute -left-[0.8rem] top-[25%] h-14 w-[3px] rounded-l bg-[#1a1a1c]" />
      <span aria-hidden className="absolute -left-[0.8rem] top-[33%] h-14 w-[3px] rounded-l bg-[#1a1a1c]" />
      <span aria-hidden className="absolute -right-[0.8rem] top-[27%] h-20 w-[3px] rounded-r bg-[#1a1a1c]" />

      {/* screen */}
      {/* Content fills the whole screen (so wallpapers run under the status bar); screens pad themselves with
          SAFE_AREA. Status bar and home indicator float above. */}
      <div className="squircle relative isolate h-full w-full overflow-hidden rounded-[var(--radius-device)] bg-bg">
        <div className="absolute inset-0">{children}</div>
        <StatusBar time={time} tone={tone} />
        <div className="pointer-events-none absolute inset-x-0 bottom-0 z-[60] flex h-8 items-center justify-center">
          <span className={`h-[5px] w-[8.5rem] rounded-full transition-colors duration-300 ${tone === "dark" ? "bg-black/80" : "bg-label/90"}`} />
        </div>
        {/* overlays (incoming call, alert sheet) cover the whole screen, status bar included */}
        {overlay}
        <div className="pointer-events-none absolute inset-x-0 top-[0.6875rem] z-50 flex justify-center">{island}</div>
      </div>
    </div>
  );
}

function StatusBar({ time, tone }: { time: string; tone: "light" | "dark" }) {
  return (
    <div
      className={`pointer-events-none absolute inset-x-0 top-0 z-[45] flex h-[3.4rem] items-center justify-between px-[2.1rem] pt-[0.35rem] transition-colors duration-300 ${
        tone === "dark" ? "text-black" : "text-label"
      }`}
    >
      <span className="w-[4.5rem] text-center text-[1.0625rem] font-semibold tracking-[-0.02em] tabular-nums">{time}</span>
      <span className="flex w-[4.5rem] items-center justify-end gap-[0.3rem]">
        <Signal className="size-[1.05rem]" strokeWidth={2.6} aria-hidden />
        <Wifi className="size-[1.05rem]" strokeWidth={2.6} aria-hidden />
        <Battery level={0.78} />
      </span>
    </div>
  );
}

function Battery({ level }: { level: number }) {
  return (
    <span role="img" aria-label={`Battery ${Math.round(level * 100)}%`} className="relative flex h-[0.8rem] w-[1.6rem] items-center">
      <span className="absolute inset-y-0 left-0 right-[0.15rem] rounded-[0.25rem] border border-current opacity-40" />
      <span
        className="absolute bottom-[0.13rem] left-[0.13rem] top-[0.13rem] rounded-[0.14rem] bg-current"
        style={{ width: `calc((100% - 0.42rem) * ${level})` }}
      />
      <span className="absolute right-0 h-[0.3rem] w-[0.1rem] rounded-r-sm bg-current opacity-40" />
    </span>
  );
}
