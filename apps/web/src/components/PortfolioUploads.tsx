"use client";
import { useState } from "react";
import { api, toError, useApi, type ApiError } from "@/lib/api/client";
import { Empty, ErrorBox, Loading } from "@/components/States";

const ACCEPT = ".md,.pdf,.py,.ts,.tsx,.js,.sql,.php";
const MAX_BYTES = 200_000;

function toBase64(buffer: ArrayBuffer): string {
  let binary = "";
  for (const byte of new Uint8Array(buffer)) binary += String.fromCharCode(byte);
  return btoa(binary);
}

/** The user's own portfolio files. Search and claim checking include them from the next run. */
export function PortfolioUploads() {
  const uploads = useApi(() => api.GET("/portfolio/uploads"), []);
  const [error, setError] = useState<ApiError>();
  const [added, setAdded] = useState<string>();
  const [busy, setBusy] = useState(false);

  async function add(input: HTMLInputElement) {
    const file = input.files?.[0];
    if (!file) return;
    setAdded(undefined);
    if (file.size > MAX_BYTES) {
      setError({ status: 422, message: `file is larger than ${MAX_BYTES / 1000} KB` });
      input.value = "";
      return;
    }
    setBusy(true);
    const body = { filename: file.name, content_base64: toBase64(await file.arrayBuffer()) };
    const r = await api.POST("/portfolio/uploads", { body });
    setBusy(false);
    input.value = "";
    if (r.error || !r.response.ok) setError(toError(r.response.status, r.error));
    else {
      setError(undefined);
      setAdded(r.data!.filename);
      void uploads.reload();
    }
  }

  async function remove(id: string) {
    const r = await api.DELETE("/portfolio/uploads/{upload_id}", { params: { path: { upload_id: id } } });
    if (!r.response.ok) setError(toError(r.response.status, r.error));
    void uploads.reload();
  }

  return (
    <section className="card space-y-2" aria-label="Portfolio">
      <h2 className="font-semibold">Your portfolio uploads</h2>
      <p className="text-xs text-muted">Markdown case studies, a PDF CV or code files, up to 200 KB each. Only you can use them as proposal evidence.</p>
      <label className="block text-sm">Add a file
        <input type="file" accept={ACCEPT} disabled={busy} onChange={(e) => void add(e.target)} className="input w-full mt-1" />
      </label>
      {added && <p role="status" className="text-sm text-good">Added {added}</p>}
      {error && <ErrorBox error={error} />}
      {uploads.loading && <Loading />}
      {uploads.error && <ErrorBox error={uploads.error} retry={uploads.reload} />}
      {uploads.data && uploads.data.length === 0 && <Empty title="No uploads yet" />}
      <ul className="divide-y divide-line">
        {(uploads.data ?? []).map((u) => (
          <li key={u.id} className="flex items-start gap-3 py-2 text-sm">
            <span className="text-xs rounded bg-panel2 px-2 py-0.5">{u.type.replace("_", " ")}</span>
            <span className="flex-1 break-words">{u.filename} <code className="text-muted text-xs">{u.id}</code></span>
            <button className="btn btn-danger" onClick={() => remove(u.id)} aria-label={`Delete upload ${u.filename}`}>Delete</button>
          </li>
        ))}
      </ul>
    </section>
  );
}
