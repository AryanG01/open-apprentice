import { useEffect, useRef, useState } from "react";
import { ApiError, get, newKey, post } from "./api";
import { DocumentView } from "./DocumentView";
import { fmt, type Point } from "./geometry";
import { firstOkPage } from "./ImportMap";
import type { Config, DocumentInfo } from "./types";

const SESSION_OTHERS = 5;

export const LIVE_UNAVAILABLE = "Live inference is unavailable. Open the recorded example.";

type Props = { docs: DocumentInfo[]; onSession: (sid: string) => void };

/** Step 2: drag labels on one document, see the engine's render, then confirm the whole document is right. */
export function Teach({ docs, onSession }: Props) {
  const ready = docs.filter((d) => firstOkPage(d)?.mapping_hash);
  const [demoId, setDemoId] = useState<string>("");
  const [moved, setMoved] = useState<Record<string, Point>>({});
  const [seen, setSeen] = useState(false);
  const [live, setLive] = useState(false);
  const [config, setConfig] = useState<Config | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const key = useRef<string>(newKey());

  useEffect(() => {
    get<Config>("/config").then(setConfig).catch(() => setConfig(null));
  }, []);
  useEffect(() => {
    if (!demoId && ready.length) setDemoId(ready[0].doc_id);
  }, [demoId, ready]);

  const demo = ready.find((d) => d.doc_id === demoId);
  const page = demo ? firstOkPage(demo) : undefined;

  const onChange = (m: Record<string, Point>, s: boolean) => {
    setMoved(m);
    setSeen(s);
    key.current = newKey(); // a new demonstration is a new action; repeats of one click reuse the same key
  };

  const submit = async () => {
    if (!demo || !page?.mapping_hash || !page.scene_hash) return;
    setBusy(true);
    setError(null);
    const boxes: Record<string, [string, string]> = {};
    for (const [k, p] of Object.entries(moved)) boxes[k] = [fmt(p.x), fmt(p.y)];
    // the session previews on a handful of other documents; reuse on the whole library comes after the skill is kept
    const others = ready.filter((d) => d.doc_id !== demo.doc_id).slice(0, SESSION_OTHERS);
    const documents = [demo, ...others].map((d) => {
      const p = firstOkPage(d);
      return { doc_id: d.doc_id, page_id: p?.page_id ?? "", mapping_hash: p?.mapping_hash ?? "" };
    });
    try {
      const r = await post<{ session_id: string }>("/sessions", {
        documents,
        demonstrations: [{ document_ref: documents.findIndex((d) => d.doc_id === demo.doc_id), before_scene_hash: page.scene_hash, boxes }],
        live,
        idempotency_key: key.current,
      });
      onSession(r.session_id);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  if (ready.length < 2) {
    return (
      <section className="v2-step" aria-labelledby="h-teach">
        <h2 id="h-teach">Show it once</h2>
        <p className="lede">Import and confirm at least two documents: you tidy one by hand, and the apprentice previews what it learned on the others before keeping it.</p>
      </section>
    );
  }
  return (
    <section className="v2-step" aria-labelledby="h-teach">
      <h2 id="h-teach">Show it once</h2>
      <p className="lede">Drag the notes on one diagram to where they belong. Every move is redrawn by the real draw.io engine.</p>
      <label className="docpick">
        Document to edit{" "}
        <select aria-label="Document to edit" value={demoId} onChange={(e) => { setDemoId(e.target.value); setMoved({}); setSeen(false); }}>
          {ready.map((d) => (
            <option key={d.doc_id} value={d.doc_id}>{d.name}</option>
          ))}
        </select>
      </label>
      {demo && page?.mapping_hash ? (
        <DocumentView key={demo.doc_id} docId={demo.doc_id} pageId={page.page_id} mappingHash={page.mapping_hash} editable title={demo.name} onChange={onChange} />
      ) : null}
      <div className="live">
        <label>
          <input type="checkbox" checked={live} disabled={!config?.live_available} onChange={(e) => setLive(e.target.checked)} /> Use the live model
        </label>
        {config && !config.live_available ? (
          <p className="note">
            {LIVE_UNAVAILABLE} A recorded run of this new flow does not exist yet; the <a href="#live">earlier prototype</a> has a recorded replay. The offline learner (no
            model) is used.
          </p>
        ) : null}
      </div>
      <button type="button" className="primary" disabled={busy || !seen || Object.keys(moved).length === 0} onClick={() => void submit()}>
        This whole document is right
      </button>
      {!seen && Object.keys(moved).length ? <p role="status">Wait for the engine's render of your edit.</p> : null}
      {error ? <p className="err" role="alert">{error}</p> : null}
    </section>
  );
}
