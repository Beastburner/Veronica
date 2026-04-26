"use client";

import { useEffect, useState } from "react";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type ModelHealth = {
  configured: boolean;
  model: string;
  base_url: string;
  provider_key_present: boolean;
};

type SystemMemory = {
  stats: { rss_mb: number; percent: number; threads: number };
  thresholds: { status: string };
  active_sessions: number;
};

export type Telemetry = {
  online: boolean;
  model: ModelHealth | null;
  system: SystemMemory | null;
  latencyMs: number | null;
  lastUpdated: number;
};

async function fetchJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, { cache: "no-store", signal });
  if (!response.ok) throw new Error(`${response.status}`);
  return response.json();
}

export function useTelemetry(intervalMs = 10_000): Telemetry {
  const [state, setState] = useState<Telemetry>({
    online: false,
    model: null,
    system: null,
    latencyMs: null,
    lastUpdated: 0,
  });

  useEffect(() => {
    const controller = new AbortController();
    let cancelled = false;

    const tick = async () => {
      const start = performance.now();
      try {
        const [model, system] = await Promise.all([
          fetchJson<ModelHealth>("/health/model", controller.signal),
          fetchJson<SystemMemory>("/system/memory", controller.signal),
        ]);
        const latencyMs = Math.round(performance.now() - start);
        if (!cancelled) {
          setState({
            online: true,
            model,
            system,
            latencyMs,
            lastUpdated: Date.now(),
          });
        }
      } catch {
        if (!cancelled) {
          setState((prev) => ({ ...prev, online: false, lastUpdated: Date.now() }));
        }
      }
    };

    void tick();
    const id = window.setInterval(tick, intervalMs);

    return () => {
      cancelled = true;
      controller.abort();
      window.clearInterval(id);
    };
  }, [intervalMs]);

  return state;
}
