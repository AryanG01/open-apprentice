import { useCallback, useEffect, useRef, useState } from "react";
import { Attempts, AxisChips, Checks, Hash, ProgramDiff, VersionTable } from "./Evidence";
import { Scene, frameOf, zoomFrame } from "./Scene";
import type { Axes, BreakResult, LiveRepair, LiveRun, LiveState, Meter, ReadyInfo, ReplayResult } from "./types";

class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

async function api<T>(path: string, method: "GET" | "POST" = "GET", body?: object, signal?: AbortSignal): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, { method, headers: body ? { "Content-Type": "application/json" } : undefined, body: body ? JSON.stringify(body) : undefined, signal });
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") throw new ApiError("Cancelled in the browser. The server may still finish that call; if it was a model call it is still billed.", 0);
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

function MeterPanel({ meter }: { meter: Meter | null }) {
  if (!meter) return null;
  return (
    <section className="meter" aria-label="Model usage">
      <h3>Model usage <span className="pill live">LIVE</span></h3>
      <dl>
        <dt>Model</dt><dd>{meter.model.split("/").pop()}</dd>
        <dt>Calls / tokens</dt><dd>{meter.session_calls} / {meter.session_tokens.toLocaleString()}</dd>
        <dt>This session</dt><dd>≈ ${meter.session_usd.toFixed(3)}</dd>
        <dt>Server total</dt><dd>${meter.server_spend_usd.toFixed(2)} of ${meter.server_cap_usd.toFixed(2)}</dd>
      </dl>
      <p className="muted small">{meter.note}{meter.unknown_cost_calls > 0 ? ` ${meter.unknown_cost_calls} call(s) reported no cost and are charged at a conservative rate.` : ""}</p>
    </section>
  );
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
  const [replay, setReplay] = useState<ReplayResult | null>(null);
  const [stress, setStress] = useState<BreakResult | null>(null);
  const [learner, setLearner] = useState<"reference" | "nemotron">("reference");
  const [modelInfo, setModelInfo] = useState<ReadyInfo["model"] | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    api<ReadyInfo>("/health/ready")
      .then((r) => {
        setReady(r.engine ? "yes" : "no");
        setReason(r.engine_error ?? "The graphics engine is not running on the server.");
        setModelInfo(r.model);
      })
      .catch((e: Error) => {
        setReady("no");
        setReason(e.message);
      });
  }, []);

  useEffect(() => {
    if (!busy) return undefined;
    const t0 = Date.now();
    setElapsed(0);
    const id = window.setInterval(() => setElapsed(Math.floor((Date.now() - t0) / 1000)), 1000);
    return () => window.clearInterval(id);
  }, [busy]);

  const guarded = useCallback(async (fn: (signal: AbortSignal) => Promise<void>) => {
    const ctl = new AbortController();
    abortRef.current = ctl;
    setBusy(true);
    setError(null);
    try {
      await fn(ctl.signal);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      abortRef.current = null;
      setBusy(false);
    }
  }, []);

  const refreshModel = () =>
    api<ReadyInfo>("/health/ready")
      .then((r) => setModelInfo(r.model))
      .catch(() => undefined);

  const start = () =>
    guarded(async (signal) => {
      setRun(null);
      setRepair(null);
      setStress(null);
      setPicked(null);
      setLive(await api<LiveState>("/api/teach", "POST", { mode: learner }, signal));
      void refreshModel();
    });

  const submit = () =>
    guarded(async (signal) => {
      if (!live?.question || !picked) return;
      setLive(await api<LiveState>(`/api/teach/${live.id}/answer`, "POST", { query_id: live.question.query_id, answer: picked, candidate_set_hash: live.question.candidate_set_hash }, signal));
      setPicked(null);
      void refreshModel();
    });

  const doRun = () =>
    guarded(async (signal) => {
      if (!live) return;
      setRepair(null);
      setRun(await api<LiveRun>(`/api/teach/${live.id}/run`, "POST", { width, backend, tool_change: toolChange && backend === "fabric" }, signal));
      void refreshModel();
    });

  const doReplay = (text: string | null) =>
    guarded(async (signal) => {
      let pkg: unknown;
      try {
        pkg = text === null ? await api<unknown>(`/api/teach/${live?.id}/evidence.json`, "GET", undefined, signal) : JSON.parse(text);
      } catch (e) {
        if (e instanceof ApiError) throw e;
        throw new ApiError("That file is not valid JSON.", 0);
      }
      setReplay(await api<ReplayResult>("/api/replay", "POST", { package: pkg }, signal));
    });

  const doBreak = () =>
    guarded(async (signal) => {
      if (!live) return;
      setStress(await api<BreakResult>(`/api/teach/${live.id}/break`, "POST", { backend, tool_change: toolChange && backend === "fabric", samples: 40, seed: Math.floor(Math.random() * 1000) }, signal));
      void refreshModel();
    });

  const doRepair = () =>
    guarded(async (signal) => {
      if (!live) return;
      setRepair(await api<LiveRepair>(`/api/teach/${live.id}/repair`, "POST", undefined, signal));
      setRun(null);
      void refreshModel();
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
        <fieldset className="runbox">
          <legend>Who proposes the rules?</legend>
          <label className="check">
            <input type="radio" name="learner" checked={learner === "reference"} onChange={() => setLearner("reference")} disabled={busy} />
            Reference learner (free, no model)
          </label>
          <label className="check">
            <input type="radio" name="learner" checked={learner === "nemotron"} onChange={() => setLearner("nemotron")} disabled={busy || !modelInfo?.available} />
            NVIDIA Nemotron (live, metered)
          </label>
          {!modelInfo?.available ? (
            <span className="muted small">Not enabled on this server{modelInfo?.error ? `: ${modelInfo.error}` : " (start it with DEMO_MODEL_ENABLED=1 and a Nebius key)"}.</span>
          ) : (
            <span className="muted small">Model: {modelInfo.id.split("/").pop()}. Server spend ${modelInfo.spend_usd.toFixed(2)} of a ${modelInfo.cap_usd.toFixed(2)} cap.</span>
          )}
        </fieldset>
        <div className="controls">
          <button className="primary" onClick={start} disabled={busy}>{live ? "Start over" : "Start teaching"}</button>
          {busy ? <button onClick={() => abortRef.current?.abort()}>Cancel</button> : null}
        </div>
        {busy ? (
          <p className="callout" role="status" aria-live="polite">
            Working… {elapsed}s elapsed{learner === "nemotron" || live?.mode === "nemotron" ? ". Waiting for the model; one call can take a minute or two." : "."}
          </p>
        ) : null}
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
            <div className="controls">
              <button onClick={doBreak} disabled={busy} title="Runs 40 generated inputs on the real engine and judges each with the independent verifier">Try to break it (40 inputs)</button>
            </div>
          </fieldset>
        ) : null}
        <p className="muted small">
          {live?.mode === "nemotron"
            ? "Nemotron proposes the rules and writes the native procedure; every output is checked on the real engine before it is accepted, and any scripted fallback is labelled. "
            : "In reference mode nothing calls a language model: rules come from a non-model learner and native procedures are scripted fixtures. "}
          Every number on the canvas is read back from the real engine.
        </p>
      </aside>

      <main className="stage" id="stage">
        <p className="eyebrow" role="status" aria-live="polite">Live · {busy ? "working…" : live ? live.state.replace(/_/g, " ").toLowerCase() : "not started"}</p>
        <h2>{!live ? "Teach it a layout rule" : concept ? "The rule is sealed. Now use it." : "Which result did you mean?"}</h2>
        {error ? <p className="callout bad" role="alert">{error}</p> : null}
        {live && live.fallbacks.length > 0 ? (
          <div className="callout" role="note"><strong>Scripted fallback used.</strong> {live.fallbacks.join(" ")}</div>
        ) : null}

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
            <button onClick={() => doReplay(null)} disabled={busy}>Re-check this package offline</button>
            <label className="btn filebtn">
              Check a package file…
              <input type="file" accept="application/json,.json" onChange={(e) => { const f = e.target.files?.[0]; if (f) void f.text().then((t) => doReplay(t)); e.target.value = ""; }} />
            </label>
            <span className="muted small">The SVG keeps every object id and carries the rule hash, backend and verifier result inside the file.</span>
          </div>
        ) : null}
        {replay ? (
          <section className={replay.passed ? "callout ok" : "callout bad"} role="note" aria-label="Offline re-check">
            <strong>{replay.passed ? "Every offline check passed." : "At least one offline check FAILED."}</strong>
            <span className="muted"> Re-derived from the package alone, with no engine and no model. It does not re-run the graphics engine.</span>
            <ul className="replay">
              {replay.checks.map((c) => (
                <li key={c.name} className={c.passed === null ? "" : c.passed ? "ok-text" : "fail-text"}>
                  <span aria-hidden="true">{c.passed === null ? "ℹ" : c.passed ? "✓" : "✗"}</span>
                  <span className="visually-hidden">{c.passed === null ? "Finding: " : c.passed ? "Passed: " : "Failed: "}</span> {c.name} <span className="muted">({c.detail})</span>
                </li>
              ))}
            </ul>
            <p className="muted small">Command line: <code>uv run python -m open_apprentice.cli replay-evidence evidence.json</code></p>
          </section>
        ) : null}

        {run && runFrame ? (
          <>
            <div className={`scenes n2`}>
              {run.canvases.map((v, i) => (
                <Scene key={v.label} view={v} frame={runFrame} ghost={i > 0 ? run.canvases[0].boxes : undefined} />
              ))}
            </div>
            {run.native_error ? <p className="callout bad" role="alert">The native procedure failed to run: {run.native_error}</p> : null}
            {run.tool_change && run.native_passed && run.verifier_passed ? (
              <p className="callout ok" role="note">
                <strong>Survived the silent tool change.</strong> This native procedure measures what the tool actually did and corrects it, so Fabric's changed behaviour did not
                break it and no repair was needed. Turn the tool change off or try again to see a procedure that does break.
              </p>
            ) : null}
            {run.tool_change && !run.native_passed ? (
              <div className="callout bad" role="note">
                <strong>Reproduced native mismatch.</strong> Your rule is unchanged, but Fabric's real result is off by the amount shown.
                <ul>{run.native_diffs.map((d) => <li key={d.key}>{d.key}: expected ({d.expected.map((n) => Math.round(n * 100) / 100).join(", ")}) observed ({d.observed.map((n) => Math.round(n * 100) / 100).join(", ")})</li>)}</ul>
                Use "Repair native procedure" on the left.
              </div>
            ) : null}
          </>
        ) : null}

        {stress ? (
          <section className={stress.failed === 0 ? "callout ok" : "callout bad"} role="note" aria-label="Stress test result">
            <strong>
              {stress.failed === 0 ? `Could not break it: ${stress.passed} of ${stress.tested} inputs passed.` : `Broke it: ${stress.failed} of ${stress.tested} inputs failed.`}
            </strong>{" "}
            On {stress.backend}{stress.tool_change ? " after the silent tool change" : ""}, using binding v{stress.binding.version} ({stress.binding.origin === "model" ? "model-generated" : "scripted fixture"}), {stress.elapsed_s}s.
            <span className="muted"> {stress.coverage}</span>
            {stress.failures.length > 0 ? (
              <div className="table-wrap">
                <table className="data">
                  <caption>First failures (width × height at x, y)</caption>
                  <thead><tr><th>Input</th><th>What failed</th><th>Expected vs observed</th></tr></thead>
                  <tbody>
                    {stress.failures.map((f, i) => (
                      <tr key={i}>
                        <td>{f.width} × {f.height} at {f.x}, {f.y}</td>
                        <td>{f.native_error ?? (f.failed_checks.join(", ").replace(/_/g, " ") || "native check")}</td>
                        <td>{f.native_diffs[0] ? `${f.native_diffs[0].key}: (${f.native_diffs[0].expected.slice(0, 2).map((n) => Math.round(n * 10) / 10).join(", ")}) vs (${f.native_diffs[0].observed.slice(0, 2).map((n) => Math.round(n * 10) / 10).join(", ")})` : "–"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : null}
          </section>
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
        <MeterPanel meter={repair?.meter ?? run?.meter ?? live?.meter ?? null} />
        <AxisChips axes={axesFor(live, run, repair)} />
        {run ? <Checks checks={run.checks} passed={run.verifier_passed} /> : null}
        {concept ? <Hash label="Sealed concept hash" value={concept.sealed_hash} /> : null}
        {run ? <Hash label={`Binding v${run.binding.version} program`} value={run.binding.program_hash} /> : null}
        {run ? <p className="muted small">Binding origin: {run.binding.origin === "model" ? "model-generated, accepted only after passing the real-backend checks" : "scripted fixture, not model-generated"}. The verifier judges against the rule you taught.</p> : null}
      </aside>
    </div>
  );
}
