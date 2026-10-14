"use client";

import { useElementSize } from "@/hooks/useElementSize";

// logical phone size in CSS px (24.375rem × 52.75rem at a 16px root) plus the rim on each side
const W = 390 + 24;
const H = 844 + 24;

/**
 * Fits the phone into whatever space the pane gives it by scaling the whole device uniformly, so text, radii and
 * layout keep their exact proportions at any window size (never larger than 1:1).
 */
export function PhoneScaler({ children }: { children: React.ReactNode }) {
  const [ref, { width, height }] = useElementSize<HTMLDivElement>();
  const scale = width && height ? Math.min(1, width / W, height / H) : 0;
  return (
    <div ref={ref} className="relative min-h-0 w-full flex-1">
      <div
        className="absolute left-1/2 top-1/2"
        style={{ transform: `translate(-50%, -50%) scale(${scale})`, opacity: scale ? 1 : 0 }}
      >
        {children}
      </div>
    </div>
  );
}
