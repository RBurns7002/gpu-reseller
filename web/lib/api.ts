// lib/api.ts
import type { Region, SimulationHistoryPoint } from "./types";

const DOCKER_INTERNAL_BASE = "http://api:8000";

function resolveBrowserBase(): string {
  if (typeof window === "undefined") {
    return "http://localhost:8000";
  }
  const protocol = window.location.protocol || "http:";
  const hostname = window.location.hostname || "localhost";
  return `${protocol}//${hostname}:8000`;
}

export function resolveApiBase(): string {
  const envBase = process.env.NEXT_PUBLIC_API_BASE;

  if (typeof window === "undefined") {
    return envBase ?? DOCKER_INTERNAL_BASE;
  }

  if (envBase) {
    try {
      const url = new URL(envBase);
      if (!["api", "api.local"].includes(url.hostname)) {
        return envBase;
      }
    } catch {
      // Ignore malformed env values and fall back to browser base.
    }
  }

  return resolveBrowserBase();
}

export function resolveWsBase(): string {
  const base = resolveApiBase();
  try {
    const url = new URL(base);
    url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
    return url.toString().replace(/\/$/, "");
  } catch {
    return base.replace("http", "ws");
  }
}

export type RegionsResponse = { regions: Region[] };

export async function fetchRegions(): Promise<RegionsResponse> {
  const base = resolveApiBase();

  try {
    const res = await fetch(`${base}/regions/latest`, { cache: "no-store" });
    if (!res.ok) {
      throw new Error(`API error: ${res.status} ${res.statusText}`);
    }
    return await res.json();
  } catch (e: any) {
    console.error("Fetch failed:", e);
    throw new Error(e?.message || "fetch failed");
  }
}

export type SimulationHistoryResponse = { points: SimulationHistoryPoint[] };

export async function fetchSimulationHistory(limit = 120): Promise<SimulationHistoryResponse> {
  const base = resolveApiBase();
  const url = new URL("/simulate/telemetry", base);
  url.searchParams.set("limit", String(limit));

  const res = await fetch(url.toString(), { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`Failed to fetch simulation history (${res.status})`);
  }
  return res.json();
}
