// web/components/FileUploader.tsx
"use client";

import * as React from "react";

export default function FileUploader() {
  const [file, setFile] = React.useState<File | null>(null);
  const [status, setStatus] = React.useState<string>("");

  const onUpload = async () => {
    try {
      if (!file) {
        setStatus("Pick a file first.");
        return;
      }
      setStatus("Requesting presigned URL...");

      // Ask the API for a presigned URL with a browser-friendly host
      const presignRes = await fetch(
        `/storage/presign-upload?bucket=user-data&key=${encodeURIComponent(file.name)}&public=1`,
        { method: "POST" }
      );
      if (!presignRes.ok) {
        const txt = await presignRes.text();
        throw new Error(`Presign error: ${presignRes.status} ${txt}`);
      }
      const presign = await presignRes.json();
      const putUrl: string = presign.browser_url || presign.url;

      setStatus("Uploading to MinIO...");
      const putRes = await fetch(putUrl, {
        method: "PUT",
        body: file,
        headers: { "Content-Type": file.type || "application/octet-stream" },
      });
      if (!putRes.ok) {
        const txt = await putRes.text();
        throw new Error(`Upload failed: ${putRes.status} ${txt}`);
      }

      setStatus(`✅ Uploaded: ${file.name}`);
    } catch (err: any) {
      setStatus(`❌ ${err?.message || err}`);
      console.error(err);
    }
  };

  return (
    <section
      style={{
        display: "flex",
        gap: 12,
        alignItems: "center",
        background: "#fafafa",
        border: "1px solid #eee",
        padding: 12,
        borderRadius: 8,
        marginBottom: 12,
      }}
    >
      <input
        type="file"
        onChange={(e) => setFile(e.target.files?.[0] || null)}
      />
      <button
        onClick={onUpload}
        style={{
          background: "#0ea5e9",
          color: "white",
          border: "none",
          borderRadius: 6,
          padding: "8px 14px",
          cursor: "pointer",
        }}
      >
        Upload to MinIO
      </button>
      <span style={{ color: "#444", fontSize: 14 }}>{status}</span>
    </section>
  );
}
