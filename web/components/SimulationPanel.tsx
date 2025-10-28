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
  resetSimulation,
  resolveWsBase,
  startSimulation,
  stopSimulation,
} from "../lib/api";
import type {
  SimulationHistoryPoint,
  SimulationStreamPayload,
  SimulationFinance,
} from "../lib/types";

const HISTORY_LIMIT = 240;
const DEFAULT_ELECTRICITY_COST = parseFloat((0.24 * 0.065).toFixed(4)); // USD per GPU-hour at 240W & $0.065/kWh

function centsToDollars(cents: number | undefined | null): number {
  if (!cents) return 0;
  return Math.round((cents / 100) * 100) / 100;
}

type ChartDatum = {
  label: string;
  timestamp: string;
  revenue: number;
  cost: number;
  profit: number;
  utilization: number;
};

type CapitalDatum = {
  label: string;
  timestamp: string;
  capital: number;
  totalSpent: number;
};

export default function SimulationPanel() {
  const [history, setHistory] = React.useState<SimulationHistoryPoint[]>([]);
  const [connected, setConnected] = React.useState(false);
  const [running, setRunning] = React.useState(false);
  const [error, setError] = React.useState<string>("");
  const [wsError, setWsError] = React.useState<string>("");

  const [stepMinutes, setStepMinutes] = React.useState(30);
  const [speedMultiplier, setSpeedMultiplier] = React.useState(3600);
  const [spendRatio, setSpendRatio] = React.useState(0.25);
  const [expansionCost, setExpansionCost] = React.useState(50000);
  const [electricityCost, setElectricityCost] = React.useState(0.065);
  const [gpuWattage, setGpuWattage] = React.useState(240);
  const [continuous, setContinuous] = React.useState(true);
  const [durationHours, setDurationHours] = React.useState(24);

  const wsBase = React.useMemo(() => resolveWsBase(), []);
  const wsRef = React.useRef<WebSocket | null>(null);
  const reconnectTimerRef = React.useRef<number | null>(null);
  const shouldReconnectRef = React.useRef(true);

  const latestPoint = React.useMemo(() => history.at(-1) ?? null, [history]);
  const latestFinance: SimulationFinance | undefined = latestPoint?.finance;

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

  const capitalData = React.useMemo<CapitalDatum[]>(() => {
    return history.map((point) => {
      const label = new Date(point.timestamp).toLocaleTimeString();
      return {
        label,
        timestamp: point.timestamp,
        capital: centsToDollars(point.finance?.capital_cents ?? latestFinance?.capital_cents ?? 0),
        totalSpent: centsToDollars(point.finance?.total_spent_cents ?? latestFinance?.total_spent_cents ?? 0),
      };
    });
  }, [history, latestFinance]);

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

  const connectWebSocket = React.useCallback(() => {
    if (typeof window === "undefined") {
      return;
    }

    if (wsRef.current) {
      wsRef.current.onclose = null;
      wsRef.current.close();
      wsRef.current = null;
    }

    const socketUrl = `${wsBase}/simulate/stream`;
    const ws = new WebSocket(socketUrl);
    wsRef.current = ws;

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
      if (shouldReconnectRef.current) {
        if (reconnectTimerRef.current) {
          window.clearTimeout(reconnectTimerRef.current);
        }
        reconnectTimerRef.current = window.setTimeout(() => {
          connectWebSocket();
        }, 2000);
      }
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
              finance: item.finance,
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
  }, [wsBase]);

  React.useEffect(() => {
    shouldReconnectRef.current = true;
    connectWebSocket();

    return () => {
      shouldReconnectRef.current = false;
      if (reconnectTimerRef.current) {
        window.clearTimeout(reconnectTimerRef.current);
      }
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [connectWebSocket]);

  const isDisabled = running;

  async function handleStart() {
    try {
      setError("");
      const body: Record<string, unknown> = {
        step_minutes: stepMinutes,
        speed_multiplier: speedMultiplier,
        spend_ratio: spendRatio,
        expansion_cost_per_gpu_cents: expansionCost,
        continuous,
        electricity_cost_per_kwh: electricityCost,
        gpu_wattage_w: gpuWattage,
      };
      if (!continuous) {
        body.duration_hours = durationHours;
      }
      setHistory([]);
      await startSimulation(body);
      setRunning(true);
    } catch (err: any) {
      setError(err?.message || "Failed to start simulation");
    }
  }

  async function handleStop() {
    try {
      setError("");
      await stopSimulation();
      setRunning(false);
    } catch (err: any) {
      setError(err?.message || "Failed to stop simulation");
    }
  }

  async function handleReset() {
    try {
      setError("");
      await resetSimulation();
      setHistory([]);
      setRunning(false);
    } catch (err: any) {
      setError(err?.message || "Failed to reset simulation");
    }
  }

  return (
    <section style={{ marginTop: 32 }}>
      <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12 }}>
          <div>
            <h2 style={{ margin: 0, fontSize: 26, fontWeight: 700 }}>Simulation Mode</h2>
            <p style={{ margin: "4px 0 0", color: "#475569" }}>
              Defaults assume $0.065/kWh electricity and 240&nbsp;W GPUs (~${DEFAULT_ELECTRICITY_COST.toFixed(4)} per GPU-hour). Adjust cost inputs to model different facilities.
            </p>
          </div>
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            <button
              onClick={handleStart}
              style={{ padding: "8px 14px", borderRadius: 8, border: "1px solid #0ea5e9", background: "#0ea5e9", color: "white" }}
            >
              Start
            </button>
            <button
              onClick={handleStop}
              style={{ padding: "8px 14px", borderRadius: 8, border: "1px solid #cbd5f5", background: "white", color: "#1e293b" }}
            >
              Stop
            </button>
            <button
              onClick={handleReset}
              style={{ padding: "8px 14px", borderRadius: 8, border: "1px solid #dc2626", background: "white", color: "#dc2626" }}
            >
              Reset Data
            </button>
          </div>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 12, alignItems: "end" }}>
          <label style={labelStyle}>
            <span>Step (minutes)</span>
            <input
              type="number"
              min={1}
              value={stepMinutes}
              onChange={(e) => setStepMinutes(Number(e.target.value))}
              disabled={isDisabled}
              style={inputStyle}
            />
          </label>
          <label style={labelStyle}>
            <span>Speed (sim seconds / real second)</span>
            <input
              type="number"
              min={1}
              value={speedMultiplier}
              onChange={(e) => setSpeedMultiplier(Number(e.target.value))}
              disabled={isDisabled}
              style={inputStyle}
            />
          </label>
          <label style={labelStyle}>
            <span>Spend Ratio (0-1)</span>
            <input
              type="number"
              min={0}
              max={1}
              step={0.05}
              value={spendRatio}
              onChange={(e) => setSpendRatio(Number(e.target.value))}
              disabled={isDisabled}
              style={inputStyle}
            />
          </label>
          <label style={labelStyle}>
            <span>Expansion Cost per GPU (cents)</span>
            <input
              type="number"
              min={1}
              value={expansionCost}
              onChange={(e) => setExpansionCost(Number(e.target.value))}
              disabled={isDisabled}
              style={inputStyle}
            />
          </label>
          <label style={labelStyle}>
            <span>Electricity ($/kWh)</span>
            <input
              type="number"
              min={0.01}
              max={0.5}
              step={0.005}
              value={electricityCost}
              onChange={(e) => setElectricityCost(Number(e.target.value))}
              disabled={isDisabled}
              style={inputStyle}
            />
          </label>
          <label style={labelStyle}>
            <span>GPU Wattage (W)</span>
            <input
              type="number"
              min={50}
              max={1000}
              step={10}
              value={gpuWattage}
              onChange={(e) => setGpuWattage(Number(e.target.value))}
              disabled={isDisabled}
              style={inputStyle}
            />
          </label>
          <label style={{ ...labelStyle, display: "flex", flexDirection: "column" }}>
            <span>Continuous Run</span>
            <input
              type="checkbox"
              checked={continuous}
              onChange={(e) => setContinuous(e.target.checked)}
              disabled={isDisabled}
              style={{ width: 18, height: 18 }}
            />
          </label>
          <label style={labelStyle}>
            <span>Duration (hours)</span>
            <input
              type="number"
              min={1}
              value={durationHours}
              onChange={(e) => setDurationHours(Number(e.target.value))}
              disabled={continuous || isDisabled}
              style={inputStyle}
            />
          </label>
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
              <YAxis yAxisId="left" stroke="#0f172a" tickFormatter={(value) => `$${value}`} allowDecimals={false} />
              <YAxis yAxisId="right" orientation="right" domain={[0, 100]} stroke="#7c3aed" tickFormatter={(value) => `${value}%`} />
              <Tooltip
                formatter={(value: number, name: string) => {
                  if (name === "utilization") {
                    return [`${value.toFixed(2)}%`, "Utilization"];
                  }
                  return [`$${value.toFixed(2)}`, name.charAt(0).toUpperCase() + name.slice(1)];
                }}
              />
              <Legend />
              <Line yAxisId="left" type="monotone" dataKey="revenue" stroke="#22c55e" strokeWidth={2} dot={false} name="revenue" />
              <Line yAxisId="left" type="monotone" dataKey="cost" stroke="#ef4444" strokeWidth={2} dot={false} name="cost" />
              <Line yAxisId="left" type="monotone" dataKey="profit" stroke="#3b82f6" strokeWidth={2} dot={false} name="profit" />
              <Line yAxisId="right" type="monotone" dataKey="utilization" stroke="#a855f7" strokeWidth={2} dot={false} name="utilization" />
            </LineChart>
          </ResponsiveContainer>
        </div>

        {history.length === 0 && (
          <p style={{ marginTop: 12, color: "#64748b" }}>
            No telemetry yet. Start the simulation to stream data.
          </p>
        )}

        {latestPoint && (
          <div style={{ marginTop: 16, display: "flex", gap: 16, flexWrap: "wrap" }}>
            <MetricCard label="Revenue" value={`$${centsToDollars(latestPoint.totals.revenue_cents).toFixed(2)}`} accent="#22c55e" />
            <MetricCard label="Cost" value={`$${centsToDollars(latestPoint.totals.cost_cents).toFixed(2)}`} accent="#ef4444" />
            <MetricCard label="Profit" value={`$${centsToDollars(latestPoint.totals.profit_cents).toFixed(2)}`} accent="#3b82f6" />
            <MetricCard label="Avg Utilization" value={`${latestPoint.totals.avg_utilization.toFixed(1)}%`} accent="#a855f7" />
            <MetricCard label="Capital" value={`$${centsToDollars(latestFinance?.capital_cents).toFixed(2)}`} accent="#0ea5e9" />
            <MetricCard label="Total Spent" value={`$${centsToDollars(latestFinance?.total_spent_cents).toFixed(2)}`} accent="#f97316" />
            <MetricCard label="New GPUs" value={`${latestFinance?.new_gpu_purchased ?? 0}`} accent="#16a34a" />
            <MetricCard
              label="Energy Cost/GPU-hr"
              value={`$${(latestFinance?.energy_cost_per_gpu_hour ?? DEFAULT_ELECTRICITY_COST).toFixed(4)}`}
              accent="#94a3b8"
            />
          </div>
        )}
      </div>

      {capitalData.length > 0 && (
        <div style={{ marginTop: 24, background: "#fff", border: "1px solid #e2e8f0", borderRadius: 16, padding: 16 }}>
          <h3 style={{ margin: 0, marginBottom: 12, fontSize: 20 }}>Capital vs Spend</h3>
          <div style={{ height: 250 }}>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={capitalData} margin={{ top: 10, right: 30, left: 0, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
                <XAxis dataKey="label" minTickGap={32} />
                <YAxis tickFormatter={(value) => `$${value}`} allowDecimals={false} />
                <Tooltip
                  formatter={(value: number, name: string) => [`$${value.toFixed(2)}`, name.replace(/([A-Z])/g, " $1").trim()]}
                />
                <Legend />
                <Line type="monotone" dataKey="capital" stroke="#0ea5e9" strokeWidth={2} dot={false} name="Capital" />
                <Line type="monotone" dataKey="totalSpent" stroke="#f97316" strokeWidth={2} dot={false} name="Total Spent" />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </section>
  );
}

type MetricProps = { label: string; value: string; accent: string };

const labelStyle: React.CSSProperties = {
  display: "flex",
  flexDirection: "column",
  fontSize: 13,
  color: "#475569",
  gap: 4,
};

const inputStyle: React.CSSProperties = {
  padding: "6px 8px",
  borderRadius: 6,
  border: "1px solid #cbd5f5",
  fontSize: 14,
};

function MetricCard({ label, value, accent }: MetricProps) {
  return (
    <div style={{ flex: "1 1 200px", borderRadius: 12, border: "1px solid #e2e8f0", padding: 16 }}>
      <div style={{ fontSize: 13, textTransform: "uppercase", letterSpacing: 0.8, color: "#64748b" }}>{label}</div>
      <div style={{ fontSize: 24, fontWeight: 700, color: accent }}>{value}</div>
    </div>
  );
}
