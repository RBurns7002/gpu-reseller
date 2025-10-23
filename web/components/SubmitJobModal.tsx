'use client';
import React, { useState } from 'react';

export default function SubmitJobModal({ open, region, onClose }:{ open:boolean; region:string|null; onClose:()=>void }){
  const [image, setImage] = useState('ghcr.io/you/your-image:latest');
  const [cmd, setCmd] = useState('python main.py');
  const [gpus, setGpus] = useState(1);
  const [queue, setQueue] = useState<'standard'|'priority'|'spot'>('standard');
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string|null>(null);

  if(!open) return null;

  const onSubmit = async () => {
    setBusy(true); setMsg(null);
    try{
      const res = await fetch(process.env.NEXT_PUBLIC_API_BASE + '/v1/jobs', {
        method: 'POST', headers: { 'Content-Type':'application/json' },
        body: JSON.stringify({ image, cmd: cmd.split(' '), gpus, gpu_model: 'DGX Spark', queue, preferred_region: region })
      });
      const j = await res.json();
      setMsg(`Job ${j.job_id} placed in ${j.region}. ETA ${j.eta_minutes}m`);
    }catch(e:any){ setMsg(e.message || 'Failed'); }
    setBusy(false);
  };

  return (
    <div className="fixed inset-0 bg-black/30 flex items-center justify-center">
      <div className="bg-white w-full max-w-xl rounded-2xl p-5">
        <div className="text-lg font-semibold">Submit job {region?`to ${region}`:''}</div>
        <div className="mt-3 grid gap-3">
          <input className="border p-2 rounded" value={image} onChange={e=>setImage(e.target.value)} />
          <input className="border p-2 rounded" value={cmd} onChange={e=>setCmd(e.target.value)} />
          <div className="flex gap-3">
            <input type="number" className="border p-2 rounded w-24" value={gpus} min={1} onChange={e=>setGpus(parseInt(e.target.value))} />
            <select className="border p-2 rounded" value={queue} onChange={e=>setQueue(e.target.value as any)}>
              <option value="standard">Standard</option>
              <option value="priority">Priority</option>
              <option value="spot">Spot</option>
            </select>
          </div>
        </div>
        <div className="mt-4 flex gap-2 justify-end">
          <button className="px-3 py-2 rounded-2xl border" onClick={onClose}>Close</button>
          <button disabled={busy} className="px-3 py-2 rounded-2xl border bg-black text-white" onClick={onSubmit}>{busy?'Submitting…':'Submit'}</button>
        </div>
        {msg && <div className="mt-3 text-sm">{msg}</div>}
      </div>
    </div>
  );
}
