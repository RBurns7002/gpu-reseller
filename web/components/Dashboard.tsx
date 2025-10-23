// web/components/Dashboard.tsx
import dynamic from "next/dynamic";
import LiveRegionTable from "./LiveRegionTable";
import type { Region } from "../lib/types";

const FileUploader = dynamic(() => import("./FileUploader"), { ssr: false });

export default function Dashboard({ data }: { data: Region[] }) {
  return (
    <main style={{ padding: "32px" }}>
      <h1 style={{ fontSize: 42, fontWeight: 800, marginBottom: 4 }}>
        GPU Reseller Regions
      </h1>
      <p style={{ margin: "0 0 20px", color: "#475569" }}>
        Streaming synthetic utilization data so the dashboard always looks alive.
      </p>

      <FileUploader />

      <LiveRegionTable initialData={data} />
    </main>
  );
}
