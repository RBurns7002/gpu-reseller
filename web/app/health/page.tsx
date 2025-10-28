"use client";

import { useEffect, useMemo, useState } from "react";
import type { CSSProperties } from "react";
import { resolveApiBase } from "../../lib/api";

type HealthResponse = {
  status: string;
  timestamp: string;
  uptime_seconds: number;
  simulation?: {
    running: boolean;
    active_clients: number;
    clients: Array<{ client: string; seconds_since_heartbeat: number | null }>;
    messages_sent: number;
    disconnects: number;
    last_broadcast: string | null;
    current_iteration: number;
    stale_timeout_seconds: number;
    request?: Record<string, any> | null;
    latest_payload?: { timestamp?: string | null; iteration?: number | null; step_hours?: number | null } | null;
  };
  containers?: ContainerHealth[];
  containers_error?: string | null;
};

type ContainerHealth = {
  name: string;
  status: string;
  restart_count?: number | null;
  health?: string | null;
  started_at?: string | null;
  error?: string;
};

function formatDuration(seconds: number | undefined): string {
  if (typeof seconds !== "number" || !Number.isFinite(seconds)) {
    return "unknown";
  }
  const s = Math.max(0, Math.floor(seconds));
  const hours = Math.floor(s / 3600);
  const minutes = Math.floor((s % 3600) / 60);
  const secs = s % 60;
  const parts = [];
  if (hours) parts.push(`${hours}h`);
  if (minutes || hours) parts.push(`${minutes}m`);
  parts.push(`${secs}s`);
  return parts.join(" ");
}

export default function HealthDashboard() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<string>("");
  const [loading, setLoading] = useState(true);

  const apiBase = useMemo(() => resolveApiBase().replace(/\/$/, ""), []);

  useEffect(() => {
    let cancelled = false;

    const fetchHealth = async () => {
      try {
        const res = await fetch(`${apiBase}/health`, { cache: "no-store" });
        if (!res.ok) {
          throw new Error(`Health request failed (${res.status})`);
        }
        const json = (await res.json()) as HealthResponse;
        if (!cancelled) {
          setHealth(json);
          setError("");
        }
      } catch (err: any) {
        if (!cancelled) {
          setError(err?.message || "Unable to load health status");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    fetchHealth();
    const timer = setInterval(fetchHealth, 5000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [apiBase]);

  const simulation = health?.simulation;
  const containers = health?.containers ?? [];
  const uptime = health ? formatDuration(health.uptime_seconds) : "";
  const lastBroadcast = simulation?.last_broadcast
    ? new Date(simulation.last_broadcast).toLocaleTimeString()
    : "N/A";

  return (
    <div style={{ padding: "2rem", fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace" }}>
      <h2 style={{ fontSize: 28, marginBottom: 16 }}>Service Health Dashboard</h2>
      {loading && <p>Loading health data...</p>}
      {error && (
        <div style={{ marginBottom: 16, color: "#dc2626" }}>Error loading health status: {error}</div>
      )}
      {health && (
        <div style={{ display: "flex", gap: 16, flexWrap: "wrap", marginBottom: 24 }}>
          <HealthMetric label="API Status" value={health.status} accent={health.status === "ok" ? "#22c55e" : "#dc2626"} />
          <HealthMetric label="Uptime" value={uptime} accent="#0ea5e9" />
          <HealthMetric
            label="Active WebSockets"
            value={String(simulation?.active_clients ?? 0)}
            accent={simulation?.active_clients ? "#16a34a" : "#6b7280"}
          />
          <HealthMetric label="Telemetry Messages" value={String(simulation?.messages_sent ?? 0)} accent="#3b82f6" />
          <HealthMetric label="Disconnects" value={String(simulation?.disconnects ?? 0)} accent="#f97316" />
          <HealthMetric label="Last Broadcast" value={lastBroadcast} accent="#a855f7" />
        </div>
      )}

      {health?.containers_error && (
        <div style={{ marginBottom: 16, color: "#dc2626" }}>
          Container inspection unavailable: {health.containers_error}
        </div>
      )}

      {containers.length > 0 && (
        <section style={{ marginBottom: 32 }}>
          <h3 style={{ marginBottom: 12, fontSize: 20 }}>Container States</h3>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                <th style={thStyle}>Name</th>
                <th style={thStyle}>Status</th>
                <th style={thStyle}>Health</th>
                <th style={thStyle}>Restarts</th>
                <th style={thStyle}>Started</th>
                <th style={thStyle}>Notes</th>
              </tr>
            </thead>
            <tbody>
              {containers.map((container) => (
                <tr key={container.name}>
                  <td style={tdStyle}>{container.name}</td>
                  <td style={tdStyle}>{container.status}</td>
                  <td style={tdStyle}>{container.health ?? "—"}</td>
                  <td style={tdStyle}>{container.restart_count ?? 0}</td>
                  <td style={tdStyle}>
                    {container.started_at ? new Date(container.started_at).toLocaleTimeString() : "—"}
                  </td>
                  <td style={tdStyle}>{container.error ?? ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {simulation && (
        <section style={{ marginBottom: 32 }}>
          <h3 style={{ marginBottom: 12, fontSize: 20 }}>Simulation State</h3>
          <pre
            style={{
              background: "#0f172a",
              color: "#f1f5f9",
              padding: 16,
              borderRadius: 12,
              overflowX: "auto",
              fontSize: 13,
            }}
          >
            {JSON.stringify(simulation, null, 2)}
          </pre>
        </section>
      )}

      {simulation?.clients && simulation.clients.length > 0 && (
        <section>
          <h3 style={{ marginBottom: 12, fontSize: 20 }}>WebSocket Connections</h3>
          <table style={{ width: "100%", borderCollapse: "collapse" }}>
            <thead>
              <tr>
                <th style={thStyle}>Client</th>
                <th style={thStyle}>Seconds Since Heartbeat</th>
              </tr>
            </thead>
            <tbody>
              {simulation.clients.map((client, idx) => (
                <tr key={`${client.client}-${idx}`}>
                  <td style={tdStyle}>{client.client}</td>
                  <td style={tdStyle}>{client.seconds_since_heartbeat ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </div>
  );
}

function HealthMetric({ label, value, accent }: { label: string; value: string; accent: string }) {
  return (
    <div
      style={{
        borderRadius: 12,
        border: "1px solid #e2e8f0",
        padding: 16,
        minWidth: 160,
        flex: "1 1 160px",
        background: "#fff",
        boxShadow: "0 4px 16px rgba(15,23,42,0.08)",
      }}
    >
      <div style={{ fontSize: 12, textTransform: "uppercase", letterSpacing: 1.2, color: "#64748b" }}>{label}</div>
      <div style={{ fontSize: 24, fontWeight: 700, marginTop: 6, color: accent }}>{value}</div>
    </div>
  );
}

const thStyle: CSSProperties = {
  textAlign: "left",
  padding: "8px 10px",
  background: "#f1f5f9",
  borderBottom: "1px solid #cbd5f5",
};

const tdStyle: CSSProperties = {
  padding: "8px 10px",
  borderBottom: "1px solid #e2e8f0",
  fontSize: 14,
};
