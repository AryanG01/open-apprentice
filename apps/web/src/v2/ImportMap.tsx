import { useEffect, useState } from "react";
import { ApiError, get, post, upload, url } from "./api";
import type { DocumentInfo, PageInfo } from "./types";

type Props = { docs: DocumentInfo[]; setDocs: (f: (d: DocumentInfo[]) => DocumentInfo[]) => void };

/** Owner-authored draw.io diagrams (provenance: docs/corpus/drawio_provenance.md) so a visitor can try the product
 *  without a file of their own. They go through exactly the same import as an upload. */
export const SAMPLES = [
  { file: "hero/order-journey.drawio", title: "Online order journey" },
  { file: "hero/hiring-process.drawio", title: "Hiring process" },
  { file: "hero/support-tickets.drawio", title: "Support tickets" },
  { file: "hero/ai-platform-map.drawio", title: "The big one: AI platform map (217 objects)" },
  { file: "training-workflow.drawio", title: "Training workflow" },
  { file: "checkout-service.drawio", title: "Checkout service" },
  { file: "microservices.drawio", title: "Microservices" },
] as const;

const baseName = (f: string) => f.split("/").pop() ?? f;

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

  const addSample = async (file: string) => {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/samples/${file}`);
      if (!res.ok) throw new Error(`the sample could not be loaded (HTTP ${res.status})`);
      const d = await upload<DocumentInfo>("/documents", new File([await res.blob()], baseName(file)));
      setDocs((all) => [...all, d]);
    } catch (e) {
      setError(`${file}: ${e instanceof ApiError ? e.message : String(e)}`);
    }
    setBusy(false);
  };

  const [progress, setProgress] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);
  const SHOWN = 12;
  /** The generated demo library (docs/corpus/library_provenance.md): uploaded through the same import, four at a time. */
  const addLibrary = async () => {
    setBusy(true);
    setError(null);
    try {
      const index = (await (await fetch("/samples/library/index.json")).json()) as { files: { file: string }[] };
      const todo = index.files.map((f) => f.file).filter((f) => !docs.some((d) => d.name === f));
      let done = 0;
      const total = todo.length;
      const one = async (f: string) => {
        const res = await fetch(`/samples/library/${f}`);
        const d = await upload<DocumentInfo>("/documents", new File([await res.blob()], f));
        setDocs((all) => [...all, d]);
        setProgress(`${++done} of ${total} diagrams imported`);
      };
      const worker = async () => {
        for (let f = todo.shift(); f; f = todo.shift()) await one(f);
      };
      // the first upload goes alone: it sets the owner cookie, and parallel first requests would each get a new owner
      const head = todo.shift();
      if (head) await one(head);
      await Promise.all([worker(), worker(), worker(), worker()]);
    } catch (e) {
      setError(`library: ${e instanceof ApiError ? e.message : String(e)}`);
    }
    setBusy(false);
  };

  const unconfirmed = docs.filter((d) => d.render === "done" && firstOkPage(d)?.mapping && !firstOkPage(d)?.mapping_hash);
  const confirmAll = async () => {
    setBusy(true);
    const todo = [...unconfirmed];
    const worker = async () => {
      for (let d = todo.shift(); d; d = todo.shift()) {
        const p = firstOkPage(d);
        if (!p) continue;
        try {
          await post(`/documents/${d.doc_id}/mapping`, { page_id: p.page_id, labels: {}, confirm: true });
          const nd = await get<DocumentInfo>(`/documents/${d.doc_id}`);
          setDocs((all) => all.map((x) => (x.doc_id === nd.doc_id ? nd : x)));
        } catch (e) {
          setError(`${d.name}: ${e instanceof ApiError ? e.message : String(e)}`);
        }
      }
    };
    await Promise.all([worker(), worker(), worker(), worker()]);
    setBusy(false);
  };

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
      <h2 id="h-import">Bring your diagrams</h2>
      <p className="lede">Add draw.io files. The apprentice reads which note belongs to which box; you check its guess.</p>
      <div className="import-row">
      <label className="file">
        Add .drawio files <input type="file" accept=".drawio,.xml" multiple disabled={busy} onChange={(e) => void add(e.target.files)} />
      </label>
      <button type="button" className="library" disabled={busy} onClick={() => void addLibrary()}>
        Load the 100-diagram library
      </button>
      {unconfirmed.length > 1 ? (
        <button type="button" disabled={busy} onClick={() => void confirmAll()}>Confirm all {unconfirmed.length} suggested mappings</button>
      ) : null}
      </div>
      {progress ? <p role="status" className="muted">{progress}</p> : null}
      {docs.filter((d) => d.render === "pending").length > 1 ? (
        <p role="status" className="muted rendering-count">{docs.filter((d) => d.render === "pending").length} diagrams still rendering in the locked engine…</p>
      ) : null}
      <p className="samples">
        Or try a sample:{" "}
        {SAMPLES.map((x) => (
          <button key={x.file} type="button" disabled={busy || docs.some((d) => d.name === baseName(x.file))}
            aria-label={`Try a sample: ${x.title}`} onClick={() => void addSample(x.file)}>
            {x.title}
          </button>
        ))}
      </p>
      {error ? <p className="err" role="alert">{error}</p> : null}
      <div className={`cards${docs.length > 6 ? " many" : ""}`}>
        {(showAll ? docs : docs.slice(0, SHOWN)).map((d) => (
          <DocCard key={d.doc_id} doc={d} compact={docs.length > 6} onUpdate={(nd) => setDocs((all) => all.map((x) => (x.doc_id === nd.doc_id ? nd : x)))} />
        ))}
      </div>
      {docs.length > SHOWN ? (
        <button type="button" className="quiet more" onClick={() => setShowAll((v) => !v)}>
          {showAll ? "Show fewer" : `Show all ${docs.length} diagrams`}
        </button>
      ) : null}
    </section>
  );
}

function DocCard({ doc, onUpdate, compact }: { doc: DocumentInfo; onUpdate: (d: DocumentInfo) => void; compact: boolean }) {
  const page = firstOkPage(doc);
  const [edits, setEdits] = useState<Record<string, { node_id?: string; role?: string }>>({});
  const [error, setError] = useState<string | null>(null);
  const nodes = page ? (page.fixed ?? []).filter((f) => !(page.reasons ?? {})[f]) : [];
  const show = (id: string) => page?.display?.[id]?.text || id;
  const swatch = (id: string) => page?.display?.[id]?.stroke || page?.display?.[id]?.fill || "transparent";

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
    <article className={`card doc${compact ? " compact" : ""}`} data-doc={doc.name}>
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
          {page.mapping && !compact ? (
            <details className="mapwrap" open={!page.mapping_hash}>
            <summary>{page.mapping_hash ? `${Object.keys(page.mapping.labels).length} notes matched to their boxes` : "Check the suggested matches"}</summary>
            <table className="mapping">
              <caption>Which box does each note describe?</caption>
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
                    <th scope="row">
                      <span className="name">{show(cell)}</span>
                      {page.mapping?.proposed.includes(cell) ? <span className="tag">suggested</span> : null}
                      <code className="id" title="cell id in the file">{cell}</code>
                    </th>
                    <td>
                      <span className="swatch" aria-hidden="true" style={{ background: swatch(edits[cell]?.node_id ?? m.node_id) }} />
                      <select aria-label={`node for ${cell}`} value={edits[cell]?.node_id ?? m.node_id}
                        onChange={(e) => setEdits((x) => ({ ...x, [cell]: { ...x[cell], node_id: e.target.value } }))}>
                        {nodes.map((n) => (
                          <option key={n} value={n}>{show(n)}</option>
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
            </details>
          ) : null}
          {page.mapping_hash ? <p className="ok">Mapping confirmed ✓</p> : <button type="button" onClick={() => void confirm()}>Confirm mapping</button>}
          {error ? <p className="err" role="alert">{error}</p> : null}
        </>
      ) : null}
    </article>
  );
}
