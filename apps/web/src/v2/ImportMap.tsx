import { useEffect, useState } from "react";
import { ApiError, get, post, upload, url } from "./api";
import type { DocumentInfo, PageInfo } from "./types";

type Props = { docs: DocumentInfo[]; setDocs: (f: (d: DocumentInfo[]) => DocumentInfo[]) => void };

export const firstOkPage = (d: DocumentInfo): PageInfo | undefined => d.pages.find((p) => p.status === "ok");

/** Step 1: add .drawio files, wait for the locked engine to render them, confirm which node each label describes. */
export function ImportMap({ docs, setDocs }: Props) {
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const pending = docs.filter((d) => d.render === "pending").map((d) => d.doc_id).join(",");

  useEffect(() => {
    if (!pending) return;
    const t = setInterval(async () => {
      for (const id of pending.split(",")) {
        try {
          const d = await get<DocumentInfo>(`/documents/${id}`);
          if (d.render !== "pending") setDocs((all) => all.map((x) => (x.doc_id === id ? d : x)));
        } catch {
          /* next tick */
        }
      }
    }, 1000);
    return () => clearInterval(t);
  }, [pending, setDocs]);

  const add = async (files: FileList | null) => {
    if (!files) return;
    setBusy(true);
    setError(null);
    for (const f of Array.from(files)) {
      try {
        const d = await upload<DocumentInfo>("/documents", f);
        setDocs((all) => [...all, d]);
      } catch (e) {
        setError(`${f.name}: ${e instanceof ApiError ? e.message : String(e)}`);
      }
    }
    setBusy(false);
  };

  return (
    <section className="v2-step" aria-labelledby="h-import">
      <h2 id="h-import">1 · Import and map</h2>
      <label className="file">
        Add .drawio files <input type="file" accept=".drawio,.xml" multiple disabled={busy} onChange={(e) => void add(e.target.files)} />
      </label>
      {error ? <p className="err" role="alert">{error}</p> : null}
      <div className="cards">
        {docs.map((d) => (
          <DocCard key={d.doc_id} doc={d} onUpdate={(nd) => setDocs((all) => all.map((x) => (x.doc_id === nd.doc_id ? nd : x)))} />
        ))}
      </div>
    </section>
  );
}

function DocCard({ doc, onUpdate }: { doc: DocumentInfo; onUpdate: (d: DocumentInfo) => void }) {
  const page = firstOkPage(doc);
  const [edits, setEdits] = useState<Record<string, { node_id?: string; role?: string }>>({});
  const [error, setError] = useState<string | null>(null);
  const nodes = page ? (page.fixed ?? []).filter((f) => !(page.reasons ?? {})[f]) : [];

  const confirm = async () => {
    if (!page) return;
    try {
      await post(`/documents/${doc.doc_id}/mapping`, { page_id: page.page_id, labels: edits, confirm: true });
      onUpdate(await get<DocumentInfo>(`/documents/${doc.doc_id}`));
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    }
  };

  return (
    <article className="card doc" data-doc={doc.name}>
      <h3>{doc.name}</h3>
      <ul className="pages">
        {doc.pages.map((p) => (
          <li key={p.page_id}>
            {p.name}: {p.status === "ok" ? "supported" : <span className="err">refused — {p.reason}</span>}
          </li>
        ))}
      </ul>
      {doc.render === "pending" ? <p role="status">Rendering in the locked engine…</p> : null}
      {doc.render === "failed" ? <p className="err" role="alert">Rendering failed: {doc.render_error}</p> : null}
      {doc.render === "done" && page ? (
        <>
          <img className="thumb" src={url(`/documents/${doc.doc_id}/pages/${page.page_id}/preview.png`)} alt={`${doc.name} preview`} />
          {page.mapping ? (
            <table className="mapping">
              <caption>Which node does each label describe?</caption>
              <thead>
                <tr>
                  <th scope="col">Label</th>
                  <th scope="col">Node</th>
                  <th scope="col">Role</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(page.mapping.labels).map(([cell, m]) => (
                  <tr key={cell}>
                    <th scope="row">{cell}{page.mapping?.proposed.includes(cell) ? " (proposed)" : ""}</th>
                    <td>
                      <select aria-label={`node for ${cell}`} value={edits[cell]?.node_id ?? m.node_id}
                        onChange={(e) => setEdits((x) => ({ ...x, [cell]: { ...x[cell], node_id: e.target.value } }))}>
                        {nodes.map((n) => (
                          <option key={n} value={n}>{n}</option>
                        ))}
                      </select>
                    </td>
                    <td>
                      <input aria-label={`role for ${cell}`} value={edits[cell]?.role ?? m.role}
                        onChange={(e) => setEdits((x) => ({ ...x, [cell]: { ...x[cell], role: e.target.value } }))} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : null}
          {page.mapping_hash ? <p className="ok">Mapping confirmed ✓</p> : <button type="button" onClick={() => void confirm()}>Confirm mapping</button>}
          {error ? <p className="err" role="alert">{error}</p> : null}
        </>
      ) : null}
    </article>
  );
}
