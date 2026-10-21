import { useEffect, useRef, useState } from "react";
import { ApiError, get, newKey, post, url } from "./api";
import { provenanceLine } from "./provenance";
import { firstOkPage } from "./ImportMap";
import type { DocRef, DocumentInfo, RunInfo, RunResult, SkillInfo } from "./types";

type Props = { docs: DocumentInfo[]; skillId: string; onCorrect: (run: RunInfo, ref: DocRef, result: RunResult) => void };

const refOf = (d: DocumentInfo): DocRef | null => {
  const p = firstOkPage(d);
  return p?.mapping_hash ? { doc_id: d.doc_id, page_id: p.page_id, mapping_hash: p.mapping_hash } : null;
};

const CHUNK = 25; // one run per 25 documents keeps each background job well inside its time limit

const STATUS_TEXT: Record<RunResult["status"], string> = { published: "Published", blocked: "Blocked", unchanged: "Unchanged", failed: "Failed" };

/** Apply the active version to chosen documents; each document gets its own receipt (three separate checks). */
export function Reuse({ docs, skillId, onCorrect }: Props) {
  const [skill, setSkill] = useState<SkillInfo | null>(null);
  const [picked, setPicked] = useState<Record<string, boolean>>({});
  const [runs, setRuns] = useState<RunInfo[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [compare, setCompare] = useState<{ run: RunInfo; docId: string; pageId: string } | null>(null);
  const key = useRef(newKey());

  const [skillTick, setSkillTick] = useState(0);
  const running = runs.some((r) => r.status === "running");
  useEffect(() => {
    get<SkillInfo>(`/skills/${skillId}`)
      .then((sk) => {
        setSkill(sk);
        // a just-committed skill is activated a moment after it is stored: look again until a version is active
        if (sk.active.version === null) setTimeout(() => setSkillTick((n) => n + 1), 1000);
      })
      .catch((e) => {
        setError(e instanceof ApiError ? e.message : String(e));
        setTimeout(() => setSkillTick((n) => n + 1), 2000);
      });
  }, [skillId, running, skillTick]);

  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const open = runs.filter((r) => r.status === "running");
    if (!open.length) return;
    const t = setTimeout(() => {
      // a failed poll is retried; it must never leave "Run running." on screen for good
      Promise.all(open.map((r) => get<RunInfo>(`/runs/${r.run_id}`)))
        .then((fresh) => setRuns((all) => all.map((r) => fresh.find((f) => f.run_id === r.run_id) ?? r)))
        .catch(() => setRetry((n) => n + 1));
    }, 1000);
    return () => clearTimeout(t);
  }, [runs, retry]);

  const ready = docs.filter((d) => refOf(d));
  const chosen = ready.filter((d) => picked[d.doc_id]);
  const apply = async () => {
    if (!skill?.active.version) return;
    setBusy(true);
    setError(null);
    const version = skill.active.version;
    const refs = chosen.map((d) => refOf(d) as DocRef);
    const made: RunInfo[] = [];
    try {
      for (let i = 0; i < refs.length; i += CHUNK) {
        const documents = refs.slice(i, i + CHUNK);
        const r = await post<{ run_id: string }>(`/skills/${skillId}/versions/${version}/apply`, {
          documents,
          idempotency_key: `${key.current}-${i / CHUNK}`,
        });
        // the run exists now: track it at once and let polling (which retries) fill in its results
        made.push({ run_id: r.run_id, skill_id: skillId, version, status: "running", documents, results: {},
          provenance: skill.provenance ?? { model: "Fixture", teacher: "You" } });
      }
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setRuns(made);
      setBusy(false);
    }
  };

  const name = (docId: string) => docs.find((d) => d.doc_id === docId)?.name ?? docId.slice(0, 8);
  const all = runs.flatMap((run) => Object.entries(run.results).map(([k, res]) => ({ run, k, res })));
  const count = (s: RunResult["status"]) => all.filter((x) => x.res.status === s).length;
  const total = runs.reduce((n, r) => n + r.documents.length, 0);

  return (
    <section className="v2-step reuse" aria-labelledby="h-reuse">
      <h2 id="h-reuse">Reuse everywhere</h2>
      {skill?.active.version ? (
        <p className="lede">
          Skill version {skill.active.version} is active. {skill.provenance ? provenanceLine(skill.provenance) : null}
        </p>
      ) : (
        <p role="status">Activating the new skill…</p>
      )}
      <fieldset className="picks">
        <legend>Apply to</legend>
        {ready.length > 3 ? (
          <button type="button" className="quiet" onClick={() => { setPicked(Object.fromEntries(ready.map((d) => [d.doc_id, true]))); key.current = newKey(); }}>
            Select all {ready.length}
          </button>
        ) : null}
        {ready.length > 3 && chosen.length ? (
          <button type="button" className="quiet" onClick={() => { setPicked({}); key.current = newKey(); }}>Select none</button>
        ) : null}
        <div className={ready.length > 6 ? "pick-grid" : ""}>
          {ready.map((d) => (
            <label key={d.doc_id} className="pick">
              <input type="checkbox" checked={!!picked[d.doc_id]} onChange={(e) => { setPicked((x) => ({ ...x, [d.doc_id]: e.target.checked })); key.current = newKey(); }}/>{" "}
              {d.name}
            </label>
          ))}
        </div>
      </fieldset>
      <button type="button" className="primary" disabled={busy || !skill?.active.version || !chosen.length} onClick={() => void apply()}>Apply</button>
      {error ? <p className="err" role="alert">{error}</p> : null}
      {runs.length ? (
        <div className="tally" role="status">
          <span className="meter" style={{ ["--done" as string]: total ? all.length / total : 0 }} aria-hidden="true" />
          <span>{all.length} of {total} checked</span>
          <span className="t-published">{count("published")} published</span>
          {count("blocked") ? <span className="t-blocked">{count("blocked")} blocked by a check</span> : null}
          {count("unchanged") ? <span>{count("unchanged")} already right</span> : null}
          {count("failed") ? <span className="t-blocked">{count("failed")} failed</span> : null}
        </div>
      ) : null}
      {runs.map((run) => (
        <div className="results wall" data-run={run.run_id} key={run.run_id}>
          <p className="muted small">
            Run {run.status}. {provenanceLine(run.provenance)}
          </p>
          {Object.entries(run.results).map(([k, res]) => {
            const [docId, pageId] = k.split(":");
            const ref = run.documents.find((d) => d.doc_id === docId && d.page_id === pageId);
            const q = `doc_id=${encodeURIComponent(docId)}&page_id=${encodeURIComponent(pageId ?? "")}`;
            const thumb = res.status === "published"
              ? url(`/runs/${run.run_id}/export?${q}&format=png`)
              : url(`/documents/${docId}/pages/${pageId}/preview.png`);
            return (
              <article key={k} className={`result ${res.status}`} data-result={name(docId)}>
                <button type="button" className="tile-img" aria-label={`Compare before and after: ${name(docId)}`} disabled={res.status !== "published"}
                  onClick={() => setCompare({ run, docId, pageId: pageId ?? "" })}>
                  <Thumb src={thumb} />
                </button>
                <h3>
                  {name(docId)}: {STATUS_TEXT[res.status]}
                </h3>
                {res.receipt ? (
                  <ul className="checks">
                    <li className={res.receipt.conformance.ok ? "y" : "n"}>{res.receipt.conformance.ok ? "✓" : "✗"} Conformance (measured positions match the rule)</li>
                    <li className={res.receipt.preservation.ok ? "y" : "n"}>{res.receipt.preservation.ok ? "✓" : "✗"} Preservation (only label positions changed)</li>
                    <li className={res.receipt.layout.ok ? "y" : "n"}>{res.receipt.layout.ok ? "✓" : "✗"} Layout safety (inside the page, no overlaps)</li>
                  </ul>
                ) : null}
                {res.reasons.length ? <p className="err">{res.reasons.join("; ")}</p> : null}
                {res.status === "published" ? (
                  <p className="downloads">
                    <a href={url(`/runs/${run.run_id}/export?${q}&format=drawio`)} download>.drawio</a>{" "}
                    <a href={url(`/runs/${run.run_id}/export?${q}&format=svg`)} download>SVG</a>{" "}
                    <a href={url(`/runs/${run.run_id}/export?${q}&format=receipt`)} download>Receipt</a>
                  </p>
                ) : null}
                {ref && res.status !== "failed" ? (
                  <button type="button" className="quiet" onClick={() => onCorrect(run, ref, res)}>Correct this document</button>
                ) : null}
              </article>
            );
          })}
        </div>
      ))}
      {compare ? <Compare {...compare} title={name(compare.docId)} onClose={() => setCompare(null)} /> : null}
    </section>
  );
}

/** A wall thumbnail: says it is rendering until the engine's image arrives, instead of showing a blank tile. */
function Thumb({ src }: { src: string }) {
  const [loaded, setLoaded] = useState(false);
  return (
    <span className={`thumbwrap${loaded ? " loaded" : ""}`}>
      {loaded ? null : <span className="thumb-wait" aria-hidden="true">rendering…</span>}
      <img src={src} alt="" loading="lazy" onLoad={() => setLoaded(true)} />
    </span>
  );
}

/** Before (the imported file) and after (the published file, as the engine rendered it), with a slider between them. */
function Compare({ run, docId, pageId, title, onClose }: { run: RunInfo; docId: string; pageId: string; title: string; onClose: () => void }) {
  const [at, setAt] = useState(50);
  const q = `doc_id=${encodeURIComponent(docId)}&page_id=${encodeURIComponent(pageId)}`;
  useEffect(() => {
    const esc = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [onClose]);
  return (
    <div className="beforeafter" role="dialog" aria-modal="true" aria-label={`Before and after: ${title}`}>
      <div className="ba-box">
        <header>
          <h3>{title}</h3>
          <button type="button" className="quiet" onClick={onClose}>Close</button>
        </header>
        <div className="slider" style={{ ["--at" as string]: `${at}%` }}>
          <img src={url(`/runs/${run.run_id}/export?${q}&format=png`)} alt={`${title} after`} />
          <img className="before" src={url(`/documents/${docId}/pages/${pageId}/preview.png`)} alt={`${title} before`} />
          <span className="handle" aria-hidden="true" />
        </div>
        <label className="range">
          Before <input type="range" min={0} max={100} value={at} onChange={(e) => setAt(Number(e.target.value))} aria-label="Before / after" /> After
        </label>
      </div>
    </div>
  );
}
