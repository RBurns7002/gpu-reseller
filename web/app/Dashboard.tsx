"use client";
import dynamic from "next/dynamic";

const FileUploader = dynamic(() => import("./FileUploader"), { ssr: false });

export default function Dashboard({ data }: { data: any[] }) {
  return (
    <div style={{ padding: "1rem" }}>
      <h2>GPU Regions</h2>

      {/* File uploader renders client-side only */}
      <FileUploader />

      <div style={{ overflowX: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              <th>Code</th>
              <th>Status</th>
              <th>Total GPUs</th>
              <th>Free GPUs</th>
              <th>Utilization (%)</th>
            </tr>
          </thead>
          <tbody>
            {data.map((r, i) => (
              <tr key={i}>
                <td>{r.code}</td>
                <td>{r.status}</td>
                <td>{r.total_gpus}</td>
                <td>{r.free_gpus}</td>
                <td>{r.utilization}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
