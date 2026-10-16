import { useMemo, useRef, useState } from "react";
import { ApiError, get, newKey, post } from "./api";
import { DocumentView } from "./DocumentView";
import { fmt, parseNum, type Point } from "./geometry";
import type { DocRef, RunInfo, RunResult, SkillInfo } from "./types";

type Props = { skillId: string; run: RunInfo; doc: DocRef; result: RunResult; title: string; onSession: (sid: string) => void; onClose: () => void };

/** Correct one document of a run: partial by default (only the labels you move), or explicit full approval. */
export function Correct({ skillId, run, doc, result, title, onSession, onClose }: Props) {
  // start from what the run produced (measured positions of the labels it moved)
  const start = useMemo(() => {
    const out: Record<string, Point> = {};
    for (const [id, row] of Object.entries(result.receipt?.conformance.labels ?? {})) {
      out[id] = { x: parseNum(row.measured[0]), y: parseNum(row.measured[1]) };
    }
    return out;
  }, [result]);
  const [moved, setMoved] = useState<Record<string, Point>>({});
  const [seen, setSeen] = useState(false);
  const [full, setFull] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const key = useRef(newKey());

  const changed = Object.fromEntries(
    Object.entries(moved).filter(([id, p]) => !start[id] || start[id].x !== p.x || start[id].y !== p.y),
  );

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      const skill = await get<SkillInfo>(`/skills/${skillId}`);
      const boxes: Record<string, [string, string]> = {};
      for (const [k, p] of Object.entries(changed)) boxes[k] = [fmt(p.x), fmt(p.y)];
      const r = await post<{ session_id: string }>(`/skills/${skillId}/corrections`, {
        base_version: skill.active.version,
        base_pointer_generation: skill.active.generation,
        run_id: run.run_id,
        doc_id: doc.doc_id,
        page_id: doc.page_id,
        boxes,
        mask: Object.keys(boxes),
        full_approval: full,
        idempotency_key: key.current,
      });
      onSession(r.session_id);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="v2-step" aria-labelledby="h-correct">
      <h2 id="h-correct">Correct {title}</h2>
      <p>Move the labels that are wrong. Only the labels you move are corrected, unless you approve the whole document.</p>
      <DocumentView docId={doc.doc_id} pageId={doc.page_id} mappingHash={doc.mapping_hash} editable title={title} start={start}
        onChange={(m, s) => { setMoved(m); setSeen(s); key.current = newKey(); }} />
      <label>
        <input type="checkbox" checked={full} onChange={(e) => setFull(e.target.checked)} /> Everything on this document is right (full approval)
      </label>
      <div className="actions">
        <button type="button" disabled={busy || !seen || Object.keys(changed).length === 0} onClick={() => void submit()}>Submit correction</button>
        <button type="button" onClick={onClose}>Back</button>
      </div>
      {error ? <p className="err" role="alert">{error}</p> : null}
    </section>
  );
}
