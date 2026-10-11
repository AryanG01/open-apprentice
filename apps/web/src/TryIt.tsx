import { useCallback, useEffect, useState } from "react";
import { Attempts, AxisChips, Checks, Hash, ProgramDiff, VersionTable } from "./Evidence";
import { Scene, frameOf, zoomFrame } from "./Scene";
import type { Axes, LiveRepair, LiveRun, LiveState } from "./types";

class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

async function api<T>(path: string, method: "GET" | "POST" = "GET", body?: object): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, { method, headers: body ? { "Content-Type": "application/json" } : undefined, body: body ? JSON.stringify(body) : undefined });
  } catch {
    throw new ApiError("The live backend is not reachable.", 0);
  }
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const j = (await res.json()) as { detail?: unknown };
      if (typeof j.detail === "string") detail = j.detail;
    } catch {
      /* not JSON: keep the status text */
    }
    throw new ApiError(detail, res.status);
  }
  return (await res.json()) as T;
}

function axesFor(s: LiveState | null, run: LiveRun | null, repair: LiveRepair | null): Axes {
  const intent = !s
    ? "Not yet resolved"
    : s.state === "INTENT_READY"
      ? "Resolved by your answer"
      : s.state === "AWAITING_USER"
        ? "Ambiguous: waiting for you"
        : "Not yet resolved";
  const native = !run
    ? "Not yet tested"
    : run.native_passed
      ? "Checked on this one input"
      : "Reproduced mismatch";
  return {
    intent,
    symbolic: s?.question
      ? s.question.source === "solver_witness"
        ? "Disagreement found by the solver and re-executed concretely"
        : "Disagreement found on a sampled scene and re-executed concretely"
      : "Not yet checked",
    native: repair?.status === "validated" ? "Repaired; checked on listed cases in both environments" : native,
    held_out: run ? "One input only; no held-out study here" : "Not yet tested",
  };
}

export function TryIt() {
  const [live, setLive] = useState<LiveState | null>(null);
  const [ready, setReady] = useState<"checking" | "yes" | "no">("checking");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [picked, setPicked] = useState<string | null>(null);
  const [width, setWidth] = useState(300);
  const [backend, setBackend] = useState<"konva" | "fabric">("konva");
  const [toolChange, setToolChange] = useState(false);
  const [run, setRun] = useState<LiveRun | null>(null);
  const [repair, setRepair] = useState<LiveRepair | null>(null);

  useEffect(() => {
    api<{ engine: boolean; engine_error: string | null }>("/health/ready")
      .then((r) => {
        setReady(r.engine ? "yes" : "no");
        setReason(r.engine_error ?? "The graphics engine is not running on the server.");
      })
      .catch((e: Error) => {
        setReady("no");
        setReason(e.message);
      });
  }, []);

  const guarded = useCallback(async (fn: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  }, []);

  const start = () =>
    guarded(async () => {
      setRun(null);
      setRepair(null);
      setPicked(null);
      setLive(await api<LiveState>("/api/teach", "POST"));
    });

  const submit = () =>
    guarded(async () => {
      if (!live?.question || !picked) return;
      setLive(await api<LiveState>(`/api/teach/${live.id}/answer`, "POST", { query_id: live.question.query_id, answer: picked, candidate_set_hash: live.question.candidate_set_hash }));
      setPicked(null);
    });

  const doRun = () =>
    guarded(async () => {
      if (!live) return;
      setRepair(null);
      setRun(await api<LiveRun>(`/api/teach/${live.id}/run`, "POST", { width, backend, tool_change: toolChange && backend === "fabric" }));
    });

  const doRepair = () =>
    guarded(async () => {
      if (!live) return;
      setRepair(await api<LiveRepair>(`/api/teach/${live.id}/repair`, "POST"));
      setRun(null);
    });

  if (ready === "checking") return <main className="page"><p role="status">Checking the live backend…</p></main>;
  if (ready === "no") {
    return (
      <main className="page">
        <div className="callout bad" role="alert">
          <strong>Live mode needs the backend.</strong> {reason} Start it from the repository root with:
          <pre tabIndex={0}>uv run uvicorn open_apprentice.api.app:app --port 8000{"\n"}npm run dev -w apps/web</pre>
          The recorded walkthrough and Compare tabs work without it.
        </div>
      </main>
    );
  }

  const q = live?.question;
  const concept = live?.concept;
  const qViews = q ? [q.base, ...q.options.map((o) => ({ label: o.id, canvas: q.base.canvas, boxes: o.boxes, note: "" }))] : [];
  const qFrame = q ? frameOf(qViews) : null;
  const qZoom = q ? zoomFrame(qViews.slice(1), "badge", 34) : null;
  const runFrame = run ? frameOf(run.canvases) : null;
  const repairNow = run?.can_repair ?? false;

  return (
    <div className="workspace try">
      <aside className="tasks" aria-label="Live controls">
        <p className="muted">Teach the badge rule yourself, then reuse it, change the tool underneath, and repair it.</p>
        <div className="controls">
          <button className="primary" onClick={start} disabled={busy}>{live ? "Start over" : "Start teaching"}</button>
        </div>
        {concept ? (
          <fieldset className="runbox">
            <legend>Reuse it</legend>
            <label>
              Card width: <strong>{width}</strong>
              <input type="range" min={60} max={600} step={10} value={width} onChange={(e) => setWidth(Number(e.target.value))} />
            </label>
            <label>
              Backend
              <select value={backend} onChange={(e) => { const b = e.target.value === "fabric" ? "fabric" : "konva"; setBackend(b); if (b === "konva") setToolChange(false); }}>
                <option value="konva">Konva</option>
                <option value="fabric">Fabric</option>
              </select>
            </label>
            <label className="check">
              <input type="checkbox" checked={toolChange && backend === "fabric"} disabled={backend !== "fabric"} onChange={(e) => setToolChange(e.target.checked)} />
              Silently change the tool (Fabric only)
            </label>
            <div className="controls">
              <button className="primary" onClick={doRun} disabled={busy}>Run</button>
              <button onClick={doRepair} disabled={busy || !repairNow}>Repair native procedure</button>
            </div>
          </fieldset>
        ) : null}
        <p className="muted small">
          Nothing here calls a language model. Candidate rules come from a non-model learner using the same teaching loop as the evaluation, and the native
          procedures are scripted fixtures. Every number on the canvas is read back from the real engine.
        </p>
      </aside>

      <main className="stage" id="stage">
        <p className="eyebrow" role="status" aria-live="polite">Live · {busy ? "working…" : live ? live.state.replace(/_/g, " ").toLowerCase() : "not started"}</p>
        <h2>{!live ? "Teach it a layout rule" : concept ? "The rule is sealed. Now use it." : "Which result did you mean?"}</h2>
        {error ? <p className="callout bad" role="alert">{error}</p> : null}

        {!live ? (
          <p className="lede">
            You will see one demonstration of a badge placed in a card's top-right corner. Several different rules fit it equally well, so the system will find an
            input where they disagree and ask you which result you meant.
          </p>
        ) : null}

        {live && !q && !concept && !live.correction ? <p className="callout" role="note">{live.note || "Could not settle on a rule."}</p> : null}

        {live ? (
          <div className="scenes n2">
            {live.demonstration.canvases.map((v, i) => (
              <Scene key={v.label} view={v} frame={frameOf(live.demonstration.canvases)} caption={i === 1 ? "sample demonstration" : undefined} />
            ))}
          </div>
        ) : null}

        {q && qFrame && qZoom ? (
          <>
            <Scene view={q.base} frame={qFrame} caption="the input in question" />
            <fieldset className="options">
              <legend>Which result did you mean? <span className="muted">(zoomed on the card's top-right corner)</span></legend>
              <div className="option-grid">
                {q.options.map((o) => (
                  <label key={o.id} className={picked === o.id ? "option picked" : "option"}>
                    <input type="radio" name="live-opt" value={o.id} checked={picked === o.id} onChange={() => setPicked(o.id)} />
                    <Scene view={{ label: `Option ${o.id}`, canvas: q.base.canvas, boxes: o.boxes, note: "" }} frame={qZoom} compact />
                  </label>
                ))}
                <label className={picked === "neither" ? "option picked neither" : "option neither"}>
                  <input type="radio" name="live-opt" value="neither" checked={picked === "neither"} onChange={() => setPicked("neither")} />
                  <span className="neither-body"><strong>Neither</strong><span>None of these.</span></span>
                </label>
              </div>
            </fieldset>
            <div className="controls"><button className="primary" onClick={submit} disabled={busy || !picked}>Submit answer</button></div>
          </>
        ) : null}

        {live?.correction ? <p className="callout" role="note">{live.correction.message}</p> : null}

        {concept ? (
          <div className="rule-card">
            <p className="muted">Learned rule (from your answer)</p>
            <p className="rule">{concept.rule_text}</p>
            <p className="muted">Teaching record: {concept.ledger_entries} entries, hash chain {concept.ledger_chain_verified ? "verified" : "NOT verified"}.</p>
          </div>
        ) : null}

        {run && live ? (
          <div className="controls export" role="group" aria-label="Export">
            <a className="btn primary" href={`/api/teach/${live.id}/export.svg`} download>Download editable SVG</a>
            <a className="btn" href={`/api/teach/${live.id}/evidence.json`} download>Evidence package (JSON)</a>
            <span className="muted small">The SVG keeps every object id and carries the rule hash, backend and verifier result inside the file.</span>
          </div>
        ) : null}

        {run && runFrame ? (
          <>
            <div className={`scenes n2`}>
              {run.canvases.map((v, i) => (
                <Scene key={v.label} view={v} frame={runFrame} ghost={i > 0 ? run.canvases[0].boxes : undefined} />
              ))}
            </div>
            {run.native_error ? <p className="callout bad" role="alert">The native procedure failed to run: {run.native_error}</p> : null}
            {run.tool_change && !run.native_passed ? (
              <div className="callout bad" role="note">
                <strong>Reproduced native mismatch.</strong> Your rule is unchanged, but Fabric's real result is off by the amount shown.
                <ul>{run.native_diffs.map((d) => <li key={d.key}>{d.key}: expected ({d.expected.map((n) => Math.round(n * 100) / 100).join(", ")}) observed ({d.observed.map((n) => Math.round(n * 100) / 100).join(", ")})</li>)}</ul>
                Use "Repair native procedure" on the left.
              </div>
            ) : null}
          </>
        ) : null}

        {repair ? (
          <>
            <p className={repair.status === "validated" ? "callout ok" : "callout bad"} role="note">
              <strong>{repair.status === "validated" ? "Repaired." : `Repair ${repair.status}.`}</strong>{" "}
              {repair.rule_unchanged ? "Your rule and its sealed hash are byte-identical; only the native procedure changed." : "The rule hash changed, so this promotion would have been refused."}
            </p>
            <Attempts attempts={repair.attempts} />
            {repair.new_program ? <ProgramDiff before={repair.old_program} after={repair.new_program} /> : null}
            <VersionTable versions={repair.versions} />
            <p className="muted">Run it again with the tool change on, or off: the repaired procedure should pass in both.</p>
          </>
        ) : null}
      </main>

      <aside className="evidence" aria-label="Evidence">
        <AxisChips axes={axesFor(live, run, repair)} />
        {run ? <Checks checks={run.checks} passed={run.verifier_passed} /> : null}
        {concept ? <Hash label="Sealed concept hash" value={concept.sealed_hash} /> : null}
        {run ? <Hash label={`Binding v${run.binding.version} program`} value={run.binding.program_hash} /> : null}
        {run ? <p className="muted small">Binding origin: {run.binding.origin} (scripted, not model-generated). The verifier judges against the rule you taught.</p> : null}
      </aside>
    </div>
  );
}
