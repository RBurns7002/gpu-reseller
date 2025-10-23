"use client";

import * as React from "react";
import { fetchRegions } from "../lib/api";
import type { Region } from "../lib/types";

type Props = {
  initialData: Region[];
  pollMs?: number;
};

const STATUS_COLORS: Record<string, string> = {
  healthy: "#22c55e",
  busy: "#f97316",
  congested: "#ef4444",
  idle: "#3b82f6",
};

export default function LiveRegionTable({ initialData, pollMs = 5000 }: Props) {
  const [regions, setRegions] = React.useState<Region[]>(initialData);
  const [trends, setTrends] = React.useState<Record<string, number>>({});
  const [lastUpdated, setLastUpdated] = React.useState<Date | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const previous = React.useRef<Region[]>(initialData);

  React.useEffect(() => {
    setRegions(initialData);
    previous.current = initialData;
    setLastUpdated(new Date());
  }, [initialData]);

  React.useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const payload = await fetchRegions();
        if (cancelled) return;

        const next = payload.regions ?? [];
        const prevMap = new Map(previous.current.map((r) => [r.code, r]));
        const deltas: Record<string, number> = {};
        next.forEach((region) => {
          const prev = prevMap.get(region.code);
          deltas[region.code] = prev
            ? region.utilization - prev.utilization
            : 0;
        });

        previous.current = next;
        setRegions(next);
        setTrends(deltas);
        setLastUpdated(new Date());
        setError(null);
      } catch (err: any) {
        if (cancelled) return;
        setError(err?.message || "fetch failed");
      }
    };

    const id = window.setInterval(load, pollMs);
    load();

    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [pollMs]);

  const renderDelta = (delta: number) => {
    if (!delta) return <span style={{ color: "#64748b" }}>0</span>;
    const color = delta > 0 ? "#ef4444" : "#22c55e";
    const prefix = delta > 0 ? "+" : "";
    const arrow = delta > 0 ? "▲" : "▼";
    return (
      <span style={{ color, fontWeight: 600 }}>
        {arrow} {prefix}
        {delta}
      </span>
    );
  };

  const statusBadge = (status: string) => {
    const color = STATUS_COLORS[status] ?? "#6b7280";
    return (
      <span
        style={{
          display: "inline-block",
          padding: "2px 8px",
          borderRadius: 999,
          background: `${color}22`,
          color,
          fontSize: 13,
          fontWeight: 600,
          textTransform: "capitalize",
        }}
      >
        {status}
      </span>
    );
  };

  return (
    <section style={{ marginTop: 20 }}>
      <header
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 12,
          gap: 12,
          flexWrap: "wrap",
        }}
      >
        <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700 }}>
          Live Region Metrics
        </h2>
        <div style={{ fontSize: 14, color: "#475569" }}>
          Refreshing every {pollMs / 1000}s
          {lastUpdated && (
            <span style={{ marginLeft: 10 }}>
              Last update: {lastUpdated.toLocaleTimeString()}
            </span>
          )}
        </div>
      </header>

      {error && (
        <div
          style={{
            background: "#fee2e2",
            border: "1px solid #fecaca",
            padding: "8px 12px",
            borderRadius: 6,
            color: "#991b1b",
            marginBottom: 12,
          }}
        >
          Live updates paused: {error}
        </div>
      )}

      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              <th style={th}>Region</th>
              <th style={th}>Status</th>
              <th style={th}>Total GPUs</th>
              <th style={th}>Free GPUs</th>
              <th style={th}>Utilization (%)</th>
              <th style={th}>Δ Utilization</th>
            </tr>
          </thead>
          <tbody>
            {regions.map((region) => (
              <tr key={region.code}>
                <td style={td}>{region.code}</td>
                <td style={td}>{statusBadge(region.status)}</td>
                <td style={td}>{region.total_gpus}</td>
                <td style={td}>{region.free_gpus}</td>
                <td style={td}>{region.utilization}</td>
                <td style={td}>{renderDelta(trends[region.code] ?? 0)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

const th: React.CSSProperties = {
  textAlign: "left",
  borderBottom: "1px solid #ddd",
  padding: "10px 8px",
  fontSize: 13,
  color: "#475569",
  textTransform: "uppercase",
  letterSpacing: 0.6,
};

const td: React.CSSProperties = {
  borderBottom: "1px solid #eee",
  padding: "10px 8px",
  fontSize: 15,
};
