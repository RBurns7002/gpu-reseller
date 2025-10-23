"use client";
import React from "react";

export default function TelemetryPanel() {
  const [data, setData] = React.useState<any>(null);
  const [error, setError] = React.useState<string>("");

  const base = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";

  async function load() {
    try {
      setError("");
      const res = await fetch(`${base}/telemetry`, { cache: "no-store" });
      if (!res.ok) throw new Error(res.statusText);
      const j = await res.json();
      setData(j);
    } catch (e:any) {
      setError(e.message || "failed");
    }
  }

  React.useEffect(() => {
    load();
    const id = setInterval(load, 5000);
    return () => clearInterval(id);
  }, []);

  return (
    <div style={{border:"1px solid #ddd", padding:"12px", borderRadius:8, marginBottom:16}}>
      <div style={{display:"flex", justifyContent:"space-between", alignItems:"center"}}>
        <h3 style={{margin:0}}>Telemetry</h3>
        <button onClick={load} style={{padding:"6px 10px"}}>Refresh</button>
      </div>
      {error && <div style={{color:"crimson", marginTop:8}}>Error: {error}</div>}
      {!data ? <div style={{opacity:.7}}>Loading…</div> : (
        <div style={{marginTop:8, fontFamily:"ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"}}>
          <div>Storage: bucket=<b>{data.storage?.bucket}</b>,
            exists=<b>{String(data.storage?.exists)}</b>,
            approx_objects=<b>{data.storage?.approx_objects ?? 0}</b>
          </div>
          <div>Status: <b>{data.status}</b>, Regions: <b>{data.regions?.length || 0}</b></div>
        </div>
      )}
    </div>
  );
}
