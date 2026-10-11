import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Compare } from "./Compare";
import { Attempts, AxisChips, Checks, Facts, ProgramDiff, VersionTable } from "./Evidence";
import { Scene, frameOf, zoomFrame } from "./Scene";
import { Home } from "./Home";
import { TryIt } from "./TryIt";
import type { Demo, Evidence, Step } from "./types";

type Mode = "Home" | "Learn" | "Reuse" | "Transfer" | "Challenge" | "Compare" | "Try it live";
const MODES: Mode[] = ["Home", "Learn", "Reuse", "Transfer", "Challenge", "Compare", "Try it live"];

const MODE_HELP: Record<Mode, string> = {
  Home: "What this is and what we measured.",
  Learn: "Show one example. It asks only when its candidate rules disagree.",
  Reuse: "Apply the frozen rule to a new input.",
  Transfer: "Carry the same rule to a second graphics backend.",
  Challenge: "The tool changes under it. Only the native procedure may be repaired.",
  Compare: "Stored live runs against baselines, with their limits.",
  "Try it live": "Teach the rule yourself on the real engines.",
};

async function loadJson<T>(name: string): Promise<T> {
  const res = await fetch(`${import.meta.env.BASE_URL}data/${name}`);
  if (!res.ok) throw new Error(`${name}: HTTP ${res.status}`);
  return (await res.json()) as T;
}

const HASH: Record<string, Mode> = {
  home: "Home", learn: "Learn", reuse: "Reuse", transfer: "Transfer", challenge: "Challenge", compare: "Compare", live: "Try it live" };

function modeFromHash(): Mode {
  return HASH[window.location.hash.replace("#", "")] ?? "Home";
}

function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

function StepBody({ step }: { step: Step }) {
  const [picked, setPicked] = useState<string | null>(null);
  useEffect(() => setPicked(null), [step.id]);

  const views = step.canvases ?? [];
  const optionViews = step.options ? [...(step.base ? [step.base] : []), ...step.options.map((o) => ({ label: o.id, canvas: { w: 0, h: 0 }, boxes: o.boxes, note: "" }))] : [];
  const frame = useMemo(() => frameOf(step.options ? optionViews : views), [step.id]); // eslint-disable-line react-hooks/exhaustive-deps
  const zoom = useMemo(() => zoomFrame(optionViews.slice(step.base ? 1 : 0), "badge", 34), [step.id]); // eslint-disable-line react-hooks/exhaustive-deps
  const expected = views.length > 1 && step.id !== "demonstrate" ? views[0].boxes : undefined;

  return (
    <>
      {views.length > 0 ? (
        <div className={`scenes n${views.length}`}>
          {views.map((v, i) => (
            <Scene key={v.label} view={v} frame={frame} ghost={i > 0 ? expected : undefined} />
          ))}
        </div>
      ) : null}

      {step.options && step.base ? (
        <>
          <Scene view={step.base} frame={frame} caption="the input in question" />
          <fieldset className="options">
            <legend>Which result did you mean? <span className="muted">(zoomed on the card's top-right corner)</span></legend>
            <div className="option-grid">
              {step.options.map((o) => (
                <label key={o.id} className={picked === o.id ? "option picked" : "option"}>
                  <input type="radio" name="opt" value={o.id} checked={picked === o.id} onChange={() => setPicked(o.id)} />
                  <Scene view={{ label: `Option ${o.id}`, canvas: step.base!.canvas, boxes: o.boxes, note: "" }} frame={zoom} compact caption={o.stands_for.join(" / ")} />
                </label>
              ))}
              <label className={picked === "neither" ? "option picked neither" : "option neither"}>
                <input type="radio" name="opt" value="neither" checked={picked === "neither"} onChange={() => setPicked("neither")} />
                <span className="neither-body"><strong>Neither</strong><span>None of these. Let me correct the example.</span></span>
              </label>
            </div>
          </fieldset>
          <p className="muted" role="status">
            {picked === null
              ? "Choose an option to continue. In this recorded walkthrough the scripted teacher answers C; your choice does not change the recording."
              : picked === "C"
                ? "Matches the recorded answer. The next step shows the rule being sealed."
                : picked === "neither"
                  ? "Neither would send the example back for a corrected demonstration and a new candidate round. That path exists in the engine but is not wired to this recorded view."
                  : "Not what the recorded teacher chose (C). Interactive answering needs the live teaching backend, which this build does not serve; the walkthrough continues from the recorded answer."}
          </p>
        </>
      ) : null}

      {step.rule_text ? (
        <div className="rule-card">
          <p className="muted">Learned rule</p>
          <p className="rule">{step.rule_text}</p>
          <p className="muted">
            Teaching record: {step.ledger_entries} entries, hash chain {step.ledger_chain_verified ? "verified" : "NOT verified"}. {step.note}
          </p>
        </div>
      ) : null}

      {step.mismatch ? (
        <div className="callout bad" role="note">
          <strong>Reproduced native mismatch.</strong> The abstract model {step.mismatch.abstract_check_passed ? "agrees with the program" : "disagrees"}, but the real backend does not.
          The abstract model is now marked {step.mismatch.semantic_model_trusted ? "trusted" : "untrusted"}. The rule is not blamed.
          <ul>
            {step.mismatch.diffs.map((d) => (
              <li key={d.key}>
                {d.key}: expected ({d.expected.map((n) => Math.round(n * 100) / 100).join(", ")}) observed ({d.observed.map((n) => Math.round(n * 100) / 100).join(", ")})
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {step.attempts ? <Attempts attempts={step.attempts} /> : null}

      {step.old_program && step.new_program ? <ProgramDiff before={step.old_program} after={step.new_program} /> : null}
      {step.versions ? <VersionTable versions={step.versions} /> : null}
      {step.rule_unchanged !== undefined ? (
        <div className={step.rule_unchanged ? "callout ok" : "callout bad"} role="note">
          <strong>{step.rule_unchanged ? "What stayed fixed:" : "Rule changed:"}</strong>{" "}
          {step.rule_unchanged
            ? "the learned rule, its teaching record and its sealed hash are byte-identical before and after the repair. Only the native procedure changed."
            : "the sealed hash differs; this promotion would have been rejected."}
        </div>
      ) : null}
    </>
  );
}

export function App() {
  const [demo, setDemo] = useState<Demo | null>(null);
  const [evidence, setEvidence] = useState<Evidence | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [index, setIndex] = useState(0);
  const [mode, setMode] = useState<Mode>(modeFromHash);
  const goHash = (h: string) => {
    window.location.hash = h;
  };
  const [playing, setPlaying] = useState(false);
  const stageRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    Promise.all([loadJson<Demo>("demo.json"), loadJson<Evidence>("evidence.json")])
      .then(([d, e]) => {
        setDemo(d);
        setEvidence(e);
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  useEffect(() => {
    const onHash = () => setMode(modeFromHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const steps = demo?.steps ?? [];
  const step = steps[index];

  const go = useCallback(
    (i: number) => {
      const next = Math.min(Math.max(i, 0), steps.length - 1);
      setIndex(next);
      if (steps[next]) setMode(steps[next].mode);
    },
    [steps],
  );

  useEffect(() => {
    if (!playing || prefersReducedMotion()) return undefined;
    if (index >= steps.length - 1) {
      setPlaying(false);
      return undefined;
    }
    const t = window.setTimeout(() => go(index + 1), 5000);
    return () => window.clearTimeout(t);
  }, [playing, index, steps.length, go]);

  const pickMode = (m: Mode) => {
    setMode(m);
    window.location.hash = Object.keys(HASH).find((k) => HASH[k] === m) ?? "";
    if (m !== "Compare" && m !== "Try it live" && m !== "Home") {
      const first = steps.findIndex((s) => s.mode === m);
      if (first >= 0) setIndex(first);
    }
  };

  if (error) {
    return (
      <main className="shell">
        <p role="alert" className="callout bad">Could not load the recorded data ({error}). Run <code>scripts/build_demo_bundle.py</code> to generate it.</p>
      </main>
    );
  }
  if (!demo || !evidence || !step) {
    return <main className="shell"><p role="status">Loading recorded data…</p></main>;
  }

  return (
    <div className="app">
      <a className="skip" href="#stage">Skip to the canvas</a>
      <header className="top">
        <div className="brand">
          <h1>Open Apprentice</h1>
          <p>Teach a layout rule once. It asks when unsure, reuses the rule across graphics backends, and repairs only the part that broke.</p>
        </div>
        {mode === "Try it live" ? (
          <div className="banner" role="note">
            <span className="pill live">LIVE ENGINE</span>
            <span>
              You are driving the real Konva and Fabric engines and the independent verifier. Choose who proposes the rules: the free reference learner (no model) or NVIDIA Nemotron
              (live and metered). Every response says which one produced what.
            </span>
          </div>
        ) : mode === "Compare" ? (
          <div className="banner" role="note">
            <span className="pill live">STORED RESULTS</span>
            <span>Rows from real Nemotron runs on the development split. Not the locked study.</span>
          </div>
        ) : mode === "Home" ? null : (
          <div className="banner" role="note">
            <span className="pill recorded">RECORDED</span>
            <span>
              Offline walkthrough on the real Konva and Fabric engines and the independent verifier. No language model is used here; the candidate rules, the teacher and the two native
              procedures are scripted.
            </span>
          </div>
        )}
        <nav aria-label="Modes">
          <ul className="tabs" role="tablist">
            {MODES.map((m) => (
              <li key={m} role="presentation">
                <button role="tab" aria-selected={mode === m} className={mode === m ? "tab on" : "tab"} onClick={() => pickMode(m)} title={MODE_HELP[m]}>
                  {m}
                </button>
              </li>
            ))}
          </ul>
        </nav>
      </header>

      {mode === "Home" ? (
        <Home data={evidence} go={goHash} />
      ) : mode === "Try it live" ? (
        <TryIt />
      ) : mode === "Compare" ? (
        <main className="page" id="stage"><Compare data={evidence} /></main>
      ) : (
        <div className="workspace">
          <aside className="tasks" aria-label="Walkthrough steps">
            <p className="muted">{MODE_HELP[mode]}</p>
            <ol>
              {steps.map((s, i) => (
                <li key={s.id}>
                  <button className={i === index ? "stepbtn on" : "stepbtn"} aria-current={i === index ? "step" : undefined} onClick={() => go(i)}>
                    <span className="stepno">{i + 1}</span>
                    <span><span className="stepmode">{s.mode}</span><span className="steptitle">{s.title}</span></span>
                  </button>
                </li>
              ))}
            </ol>
            <div className="controls">
              <button onClick={() => go(index - 1)} disabled={index === 0}>Back</button>
              <button className="primary" onClick={() => go(index + 1)} disabled={index === steps.length - 1}>Next</button>
              <button onClick={() => setPlaying((p) => !p)} aria-pressed={playing} disabled={prefersReducedMotion()} title={prefersReducedMotion() ? "Autoplay is off because your system asks for reduced motion" : ""}>
                {playing ? "Pause" : "Autoplay"}
              </button>
            </div>
            <p className="muted small">Nothing is running live. Each step shows stored output, so there is no progress bar and no Cancel.</p>
          </aside>

          <main className="stage" id="stage" ref={stageRef} tabIndex={-1}>
            <p className="eyebrow" role="status" aria-live="polite">{`Step ${index + 1} of ${steps.length} · ${step.mode}`}</p>
            <h2>{step.title}</h2>
            <p className="lede">{step.summary}</p>
            <StepBody step={step} />
          </main>

          <aside className="evidence" aria-label="Evidence">
            <AxisChips axes={step.axes} />
            {step.checks ? <Checks checks={step.checks} passed={step.verifier_passed} /> : null}
            <Facts step={step} />
            {step.same_concept_hash !== undefined ? (
              <p className={step.same_concept_hash ? "ok-text" : "fail-text"}>
                <span aria-hidden="true">{step.same_concept_hash ? "✓" : "✗"}</span> Same concept hash on both backends: {step.same_concept_hash ? "yes" : "no"}
              </p>
            ) : null}
            {step.binding ? <p className="muted small">Binding origin: {step.binding.origin} (a scripted fixture, not model-generated). Scope: {step.binding.scope}.</p> : null}
          </aside>
        </div>
      )}

      <footer className="foot">
        <p>
          Walkthrough recorded {demo.generated_at.slice(0, 16).replace("T", " ")} UTC. "Try it live" needs the local API; Nemotron mode additionally needs
          DEMO_MODEL_ENABLED=1 and a Nebius key. Not built yet: your own scenes, a skill inspector, SVG import, and entering a corrected example after "Neither". Compare reads stored results only.
        </p>
      </footer>
    </div>
  );
}
