"use client";

import { AnimatePresence, motion } from "motion/react";
import { useEffect, useState } from "react";
import { Keyboard, X } from "lucide-react";
import { spring } from "@/config/motion";

const GROUPS: { title: string; items: [string, string][] }[] = [
  {
    title: "Session",
    items: [
      ["Space", "Play / pause"],
      ["← →", "Step one event"],
      ["R", "Restart"],
      ["1 – 8", "Switch scenario"],
    ],
  },
  {
    title: "Anywhere",
    items: [
      ["?", "Show these shortcuts"],
      ["Esc", "Close menus and sheets"],
    ],
  },
  {
    title: "Pointer",
    items: [
      ["Click an event", "Jump there on the timeline"],
      ["Drag the playhead", "Scrub through the session"],
      ["Click a feed row", "Inspect the raw API exchange"],
      ["Click a wall tile", "Open that customer's session"],
    ],
  },
];

/** Keyboard shortcuts as a centred sheet over a dimmed scrim (opened with "?" or the keyboard button). */
export function ShortcutsSheet() {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (t?.closest("input, textarea, [contenteditable]")) return;
      if (e.key === "?") setOpen((o) => !o);
      else if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        aria-label="Keyboard shortcuts (?)"
        title="Keyboard shortcuts (?)"
        className="flex size-9 items-center justify-center rounded-full bg-fill-tertiary text-label-secondary transition-[scale,background-color,color] hover:bg-fill-secondary hover:text-label active:scale-[0.92]"
      >
        <Keyboard className="size-4" />
      </button>
      <AnimatePresence>
        {open && (
          <motion.div
            className="fixed inset-0 z-[90] flex items-center justify-center bg-black/55 p-6"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onPointerDown={(e) => e.target === e.currentTarget && setOpen(false)}
          >
            <motion.div
              role="dialog"
              aria-modal
              aria-label="Keyboard shortcuts"
              initial={{ opacity: 0, scale: 0.94, y: 12, filter: "blur(8px)" }}
              animate={{ opacity: 1, scale: 1, y: 0, filter: "blur(0px)" }}
              exit={{ opacity: 0, scale: 0.97, y: 8, filter: "blur(6px)" }}
              transition={spring.sheet}
              className="squircle w-full max-w-[34rem] rounded-[1.75rem] bg-[#1c1c1e]/95 p-6 shadow-[inset_0_0.5px_0_rgb(255_255_255/0.12),0_40px_100px_rgb(0_0_0/0.6)] backdrop-blur-2xl"
            >
              <div className="mb-4 flex items-center justify-between">
                <h2 className="text-title-3">Keyboard shortcuts</h2>
                <button aria-label="Close" onClick={() => setOpen(false)} className="flex size-8 items-center justify-center rounded-full bg-fill-tertiary transition-[scale] active:scale-90">
                  <X className="size-4" />
                </button>
              </div>
              <div className="flex flex-col gap-5">
                {GROUPS.map((g) => (
                  <section key={g.title}>
                    <h3 className="mb-2 text-eyebrow text-label-tertiary">{g.title}</h3>
                    <dl className="grid grid-cols-[auto_1fr] items-center gap-x-4 gap-y-2">
                      {g.items.map(([k, v]) => (
                        <div key={k} className="contents">
                          <dt>
                            <kbd className="rounded-[0.45rem] bg-fill-tertiary px-2 py-0.5 font-sans text-footnote font-semibold shadow-[inset_0_-1px_0_rgb(0_0_0/0.4)]">{k}</kbd>
                          </dt>
                          <dd className="text-subheadline text-label-secondary">{v}</dd>
                        </div>
                      ))}
                    </dl>
                  </section>
                ))}
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
