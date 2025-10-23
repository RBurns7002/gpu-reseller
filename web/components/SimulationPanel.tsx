"use client";

import React from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  fetchSimulationHistory,
  resolveApiBase,
  resolveWsBase,
} from "../lib/api";
import type {
  SimulationHistoryPoint,
  SimulationStreamPayload,
} from "../lib/types";

type ChartDatum = {
  label: string;
  timestamp: string;
  revenue: number;
  cost: number;
  profit: number;
  utilization: number;
};

const HISTORY_LIMIT = 120;

function centsToDollars(cents: number): number {
  return Math.round((cents / 100) * 100) / 100;
}

export default function SimulationPanel() {
  const [history, setHistory] = React.useState<SimulationHistoryPoint[]>([]);
  const [connected, setConnected] = React.useState(false);
  const [running, setRunning] = React.useState(false);
  const [error, setError] = React.useState<string>("");
  const [wsError, setWsError] = React.useState<string>("");

  const latestPoint = history.at(-1);

  const chartData = React.useMemo<ChartDatum[]>(() => {
    return history.map((point) => {
      const label = new Date(point.timestamp).toLocaleTimeString();
      return {
        label,
        timestamp: point.timestamp,
        revenue: centsToDollars(point.totals.revenue_cents),
        cost: centsToDollars(point.totals.cost_cents),
        profit: centsToDollars(point.totals.profit_cents),
        utilization: Number(point.totals.avg_utilization.toFixed(2)),
      };
    });
  }, [history]);

  const apiBase = React.useMemo(() => resolveApiBase(), []);

  React.useEffect(() => {
    let cancelled = false;
    fetchSimulationHistory()
      .then((res) => {
        if (!cancelled) {
          const sorted = (res.points ?? []).slice().sort((a, b) =>
            a.timestamp.localeCompare(b.timestamp)
          );
          setHistory(sorted);
        }
      })
      .catch((err) => {
        console.error("Failed to load simulation history", err);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  React.useEffect(() => {
    if (typeof window === "undefined") return;

    const socketUrl = `${resolveWsBase()}/simulate/stream`;
    const ws = new WebSocket(socketUrl);

    ws.onopen = () => {
      setConnected(true);
      setWsError("");
    };

    ws.onerror = (event) => {
      console.error("Simulation websocket error", event);
      setWsError("WebSocket connection error");
    };

    ws.onclose = () => {
      setConnected(false);
      setRunning(false);
    };

    ws.onmessage = (event) => {
      try {
        const payload: SimulationStreamPayload = JSON.parse(event.data);
        setRunning(true);
        setHistory((prev) => {
          const merged = [...prev, payload];
          const dedup = new Map<string, SimulationHistoryPoint>();
          merged.forEach((item) => {
            dedup.set(item.timestamp, {
              timestamp: item.timestamp,
              totals: item.totals,
              regions: item.regions,
            });
          });
          const ordered = Array.from(dedup.values()).sort((a, b) =>
            a.timestamp.localeCompare(b.timestamp)
          );
          return ordered.slice(-HISTORY_LIMIT);
        });
      } catch (err) {
        console.error("Failed to parse simulation payload", err);
      }
    };

    return () => {
      ws.close();
    };
  }, []);

  async function startSimulation() {
    try {
      setError("");
      const res = await fetch(`${apiBase}/simulate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ duration_hours: 24, step_minutes: 60, speed_multiplier: 3600 }),
      });
      if (!res.ok) {
        const message = await res.text();
        throw new Error(message || "Failed to start simulation");
      }
      setRunning(true);
    } catch (err: any) {
      setError(err?.message || "Failed to start simulation");
    }
  }

  async function stopSimulation() {
    try {
      setError("");
      await fetch(`${apiBase}/simulate/stop`, { method: "POST" });
      setRunning(false);
    } catch (err: any) {
      setError(err?.message || "Failed to stop simulation");
    }
  }

  return (
    <section style={{ marginTop: 32 }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 26, fontWeight: 700 }}>Simulation Mode</h2>
          <p style={{ margin: "4px 0 0", color: "#475569" }}>
            Accelerated telemetry at 1 hour per second. Watch revenue and utilization update in real time.
          </p>
        </div>
        <div style={{ display: "flex", gap: 8 }}>
          <button
            onClick={startSimulation}
            style={{ padding: "8px 14px", borderRadius: 8, border: "1px solid #0ea5e9", background: "#0ea5e9", color: "white" }}
          >
            Start Simulation
          </button>
          <button
            onClick={stopSimulation}
            style={{ padding: "8px 14px", borderRadius: 8, border: "1px solid #cbd5f5", background: "white", color: "#1e293b" }}
          >
            Stop
          </button>
        </div>
      </div>

      <div style={{ marginTop: 12, fontSize: 14, color: "#475569" }}>
        WebSocket: {connected ? <span style={{ color: "#22c55e", fontWeight: 600 }}>connected</span> : "disconnected"} · Simulation status: {running ? "running" : "idle"}
      </div>
      {error && <div style={{ marginTop: 8, color: "#dc2626" }}>{error}</div>}
      {wsError && <div style={{ marginTop: 8, color: "#dc2626" }}>{wsError}</div>}

      <div style={{ marginTop: 24, background: "#fff", border: "1px solid #e2e8f0", borderRadius: 16, padding: 16 }}>
        <div style={{ height: 320 }}>
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="label" minTickGap={32} />
              <YAxis yAxisId="left" stroke="#0f172a" tickFormatter={(value) => `$${value}`} />
              <YAxis yAxisId="right" orientation="right" domain={[0, 100]} stroke="#7c3aed" tickFormatter={(value) => `${value}%`} />
              <Tooltip formatter={(value: number, name: string) => {
                if (name === "utilization") {
                  return [`${value.toFixed(2)}%`, "Utilization"];
                }
                return [`$${value.toFixed(2)}`, name.charAt(0).toUpperCase() + name.slice(1)];
              }} />
              <Legend />
              <Line yAxisId="left" type="monotone" dataKey="revenue" stroke="#22c55e" strokeWidth={2} dot={false} name="revenue" />
              <Line yAxisId="left" type="monotone" dataKey="cost" stroke="#ef4444" strokeWidth={2} dot={false} name="cost" />
              <Line yAxisId="left" type="monotone" dataKey="profit" stroke="#3b82f6" strokeWidth={2} dot={false} name="profit" />
              <Line yAxisId="right" type="monotone" dataKey="utilization" stroke="#a855f7" strokeWidth={2} dot={false} name="utilization" />
            </LineChart>
          </ResponsiveContainer>
        </div>

        {latestPoint && (
          <div style={{ marginTop: 16, display: "flex", gap: 16, flexWrap: "wrap" }}>
            <MetricCard label="Revenue" value={`$${centsToDollars(latestPoint.totals.revenue_cents).toFixed(2)}`} accent="#22c55e" />
            <MetricCard label="Cost" value={`$${centsToDollars(latestPoint.totals.cost_cents).toFixed(2)}`} accent="#ef4444" />
            <MetricCard label="Profit" value={`$${centsToDollars(latestPoint.totals.profit_cents).toFixed(2)}`} accent="#3b82f6" />
            <MetricCard label="Avg Utilization" value={`${latestPoint.totals.avg_utilization.toFixed(1)}%`} accent="#a855f7" />
          </div>
        )}
      </div>
    </section>
  );
}

function MetricCard({ label, value, accent }: { label: string; value: string; accent: string }) {
  return (
    <div style={{ flex: "1 1 200px", borderRadius: 12, border: "1px solid #e2e8f0", padding: 16 }}>
      <div style={{ fontSize: 13, textTransform: "uppercase", letterSpacing: 0.8, color: "#64748b" }}>{label}</div>
      <div style={{ fontSize: 24, fontWeight: 700, color: accent }}>{value}</div>
    </div>
  );
}
