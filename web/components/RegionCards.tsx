'use client';
import React from 'react';

type Item = {
  region: string;
  status: string;
  total_gpus: number;
  free_gpus: number;
  utilization: number;
  est_wait_minutes: { priority: number; standard: number; spot: number };
  prices: { standard_cph: number; priority_cph: number; spot_cph: number };
};

export default function RegionCards({ data, onSelect }:{ data: Item[]; onSelect:(r:string)=>void }) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {data.map((r) => (
        <div key={r.region} className="rounded-2xl shadow p-4 border">
          <div className="flex items-center justify-between">
            <h3 className="text-xl font-semibold capitalize">{r.region}</h3>
            <span className={`px-2 py-1 rounded text-sm ${r.status==='healthy'?'bg-green-100':'bg-yellow-100'}`}>{r.status}</span>
          </div>
          <div className="mt-2 text-sm opacity-80">Utilization: {(r.utilization*100).toFixed(0)}% · Free GPUs: {r.free_gpus}</div>
          <div className="mt-3 grid grid-cols-3 gap-2 text-sm">
            <div className="p-2 rounded bg-gray-50">
              <div className="font-medium">Standard</div>
              <div>${r.prices.standard_cph.toFixed(2)}/hr</div>
              <div>ETA {r.est_wait_minutes.standard}m</div>
            </div>
            <div className="p-2 rounded bg-gray-50">
              <div className="font-medium">Priority</div>
              <div>${r.prices.priority_cph.toFixed(2)}/hr</div>
              <div>ETA {r.est_wait_minutes.priority}m</div>
            </div>
            <div className="p-2 rounded bg-gray-50">
              <div className="font-medium">Spot</div>
              <div>${r.prices.spot_cph.toFixed(2)}/hr</div>
              <div>ETA {r.est_wait_minutes.spot}m</div>
            </div>
          </div>
          <button onClick={()=>onSelect(r.region)} className="mt-4 w-full rounded-2xl border px-3 py-2 hover:bg-gray-50">Submit here</button>
        </div>
      ))}
    </div>
  );
}
