"use client";

import { useEffect, useState } from "react";

/**
 * Content-box size of an element, kept current with a ResizeObserver. Returns a callback ref, so it follows the
 * element when it unmounts and remounts (a collapsible panel, a keyed chart).
 */
export function useElementSize<T extends HTMLElement>() {
  const [node, setNode] = useState<T | null>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });
  useEffect(() => {
    if (!node) return;
    const ro = new ResizeObserver(([e]) => setSize({ width: e.contentRect.width, height: e.contentRect.height }));
    ro.observe(node);
    return () => ro.disconnect();
  }, [node]);
  return [setNode, size] as const;
}
