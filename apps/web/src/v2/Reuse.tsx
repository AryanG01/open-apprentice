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

/** Apply the active version to chosen documents; each document gets its own receipt (three separate checks). */
export function Reuse({ docs, skillId, onCorrect }: Props) {
  const [skill, setSkill] = useState<SkillInfo | null>(null);
  const [picked, setPicked] = useState<Record<string, boolean>>({});
  const [run, setRun] = useState<RunInfo | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const key = useRef(newKey());

  const [skillTick, setSkillTick] = useState(0);
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
  }, [skillId, run?.status, skillTick]);

  const [retry, setRetry] = useState(0);
  useEffect(() => {
    if (!run || run.status !== "running") return;
    const t = setTimeout(() => {
      // a failed poll is retried; it must never leave "Run running." on screen for good
      get<RunInfo>(`/runs/${run.run_id}`).then(setRun).catch(() => setRetry((n) => n + 1));
    }, 1000);
    return () => clearTimeout(t);
  }, [run, retry]);

  const ready = docs.filter((d) => refOf(d));
  const apply = async () => {
    if (!skill?.active.version) return;
    setBusy(true);
    setError(null);
    try {
      const documents = ready.filter((d) => picked[d.doc_id]).map((d) => refOf(d) as DocRef);
      const r = await post<{ run_id: string }>(`/skills/${skillId}/versions/${skill.active.version}/apply`, { documents, idempotency_key: key.current });
      // the run exists now: track it at once and let polling (which retries) fill in its results
      setRun({ run_id: r.run_id, skill_id: skillId, version: skill.active.version, status: "running", documents, results: {},
        provenance: skill.provenance ?? { model: "Fixture", teacher: "You" } });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const name = (docId: string) => docs.find((d) => d.doc_id === docId)?.name ?? docId.slice(0, 8);

  return (
    <section className="v2-step" aria-labelledby="h-reuse">
      <h2 id="h-reuse">3 · Reuse and export</h2>
      {skill?.active.version ? (
        <p>
          Skill version {skill.active.version} is active. {skill.provenance ? provenanceLine(skill.provenance) : null}
        </p>
      ) : (
        <p role="status">Activating the new skill…</p>
      )}
      <fieldset>
        <legend>Apply to</legend>
        {ready.map((d) => (
          <label key={d.doc_id} className="pick">
            <input type="checkbox" checked={!!picked[d.doc_id]} onChange={(e) => { setPicked((x) => ({ ...x, [d.doc_id]: e.target.checked })); key.current = newKey(); }} />{" "}
            {d.name}
          </label>
        ))}
      </fieldset>
      <button type="button" disabled={busy || !skill?.active.version || !Object.values(picked).some(Boolean)} onClick={() => void apply()}>Apply</button>
      {error ? <p className="err" role="alert">{error}</p> : null}
      {run ? (
        <div className="results" data-run={run.run_id}>
          <p>
            Run {run.status}. {provenanceLine(run.provenance)}
          </p>
          {Object.entries(run.results).map(([k, res]) => {
            const [docId, pageId] = k.split(":");
            const ref = run.documents.find((d) => d.doc_id === docId && d.page_id === pageId);
            const q = `doc_id=${encodeURIComponent(docId)}&page_id=${encodeURIComponent(pageId ?? "")}`;
            return (
              <article key={k} className={`result ${res.status}`} data-result={name(docId)}>
                <h3>
                  {name(docId)}: {res.status === "published" ? "Published" : res.status === "blocked" ? "Blocked" : res.status === "unchanged" ? "Unchanged" : "Failed"}
                </h3>
                {res.receipt ? (
                  <ul className="checks">
                    <li>{res.receipt.conformance.ok ? "✓" : "✗"} Conformance (measured positions match the rule)</li>
                    <li>{res.receipt.preservation.ok ? "✓" : "✗"} Preservation (only label positions changed)</li>
                    <li>{res.receipt.layout.ok ? "✓" : "✗"} Layout safety (inside the page, no overlaps)</li>
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
                  <button type="button" onClick={() => onCorrect(run, ref, res)}>Correct this document</button>
                ) : null}
              </article>
            );
          })}
        </div>
      ) : null}
    </section>
  );
}
