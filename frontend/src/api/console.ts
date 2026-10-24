"use client";

import { useEffect, useState } from "react";
import type { ModelReport, Traffic } from "@/types/console";

const cache = new Map<string, Promise<unknown>>();

function load<T>(url: string): Promise<T> {
  if (!cache.has(url)) {
    cache.set(url, fetch(url).then((r) => {
      if (!r.ok) throw new Error(`${url}: ${r.status}`);
      return r.json();
    }).catch((e) => {
      cache.delete(url);
      throw e;
    }));
  }
  return cache.get(url) as Promise<T>;
}

function useJson<T>(url: string): { data: T | null; error: string | null } {
  const [state, setState] = useState<{ data: T | null; error: string | null }>({ data: null, error: null });
  useEffect(() => {
    let live = true;
    load<T>(url).then((data) => live && setState({ data, error: null }), (e: Error) => live && setState({ data: null, error: e.message }));
    return () => {
      live = false;
    };
  }, [url]);
  return state;
}

/** One held-out test day replayed through the trained service (backend/record_auth_traffic.py). */
export const useTraffic = () => useJson<Traffic>("/data/auth_traffic.json");

/** Evaluation reports in one file (backend/export_console_report.py). */
export const useReport = () => useJson<ModelReport>("/data/model_report.json");
