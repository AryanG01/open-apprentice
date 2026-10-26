import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { CampaignLane } from "./CampaignLane";
import { Compare } from "./Compare";
import { Attempts, AxisChips, Checks, Facts, ProgramDiff, VersionTable } from "./Evidence";
import { Scene, frameOf, zoomFrame } from "./Scene";
import { Home } from "./Home";
import { SvgLane } from "./SvgLane";
import { TryIt } from "./TryIt";
import { Apprentice } from "./v2/Apprentice";
import type { Demo, Evidence, Step } from "./types";
import { Adapt } from "./Adapt";

type Mode = "Home" | "Learn" | "Reuse" | "Transfer" | "Challenge" | "Compare" | "Try it live" | "Real SVG" | "Campaign";
const MODES: Mode[] = ["Home", "Learn", "Reuse", "Transfer", "Challenge", "Compare", "Try it live", "Real SVG", "Campaign"];

const MODE_HELP: Record<Mode, string> = {
  Home: "What this is and what we measured.",
  Learn: "Show one example. It asks only when its candidate rules disagree.",
  Reuse: "Apply the frozen rule to a new input.",
  Transfer: "Carry the same rule to a second graphics backend.",
  Challenge: "The tool changes under it. Only the native procedure may be repaired.",
  Compare: "Stored live runs against baselines, with their limits.",
  "Try it live": "Teach the rule yourself on the real engines.",
  "Real SVG": "Apply your taught rule to a real SVG document (experimental).",
  Campaign: "Teach a banner-to-story layout once; it asks when the copy does not fit (development fixtures).",
};

async function loadJson<T>(name: string): Promise<T> {
  const res = await fetch(`${import.meta.env.BASE_URL}data/${name}`);
  if (!res.ok) throw new Error(`${name}: HTTP ${res.status}`);
  return (await res.json()) as T;
}

const HASH: Record<string, Mode> = {
  home: "Home", learn: "Learn", reuse: "Reuse", transfer: "Transfer", challenge: "Challenge", compare: "Compare", live: "Try it live", svg: "Real SVG", campaign: "Campaign" };

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

function Prototype() {
  const [demo, setDemo] = useState<Demo | null>(null);
  const [evidence, setEvidence] = useState<Evidence | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [index, setIndex] = useState(0);
  const [mode, setMode] = useState<Mode>(modeFromHash);
  const goHash = (h: string) => {
    window.location.hash = h;
  };
  const [playing, setPlaying] = useState(false);
  const [backend, setBackend] = useState<"checking" | "yes" | "no">("checking");
  useEffect(() => {
    fetch("/health/ready")
      .then((r) => (r.ok ? (r.json() as Promise<{ engine?: boolean }>) : Promise.reject(new Error("no api"))))
      .then((j) => setBackend(j.engine ? "yes" : "no"))
      .catch(() => setBackend("no"));
  }, []);
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
    if (m !== "Compare" && m !== "Try it live" && m !== "Home" && m !== "Real SVG" && m !== "Campaign") {
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
      <header className="top">
        <div className="brand">
          <h1>Open Apprentice</h1>
          <p>Teach a layout rule once. It asks when unsure, reuses the rule across graphics backends, and repairs only the part that broke.</p>
        </div>
        {(mode === "Try it live" || mode === "Real SVG" || mode === "Campaign") && backend === "no" ? (
          <div className="banner" role="note">
            <span className="pill recorded">NOT AVAILABLE IN THIS COPY</span>
            <span>
              This copy is a static preview with no backend. The live engine needs Python and real browser engines, so it runs only locally or on a full server.
              Home, the walkthrough and Compare work here.
            </span>
          </div>
        ) : mode === "Try it live" ? (
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
        ) : mode === "Real SVG" ? (
          <div className="banner" role="note">
            <span className="pill recorded">EXPERIMENTAL</span>
            <span>Applies the rule you taught to owner-authored SVG files. No language model is used; geometry is verified by measuring in the locked browser.</span>
          </div>
        ) : mode === "Campaign" ? (
          <div className="banner" role="note">
            <span className="pill recorded">DEVELOPMENT</span>
            <span>
              Runs on the real Konva engine with authored development banners (not held out). No language model is used: the layout is learned by search, and the two overflow
              outcomes are built in and labelled so.
            </span>
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

      {mode === "Campaign" ? (
        <CampaignLane />
      ) : mode === "Real SVG" ? (
        <SvgLane go={goHash} />
      ) : mode === "Home" ? (
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
          This is the first-week prototype: placing a badge on a card, taught once and reused across two graphics engines. The recorded walkthrough was made{" "}
          {demo.generated_at.slice(0, 10)}. "Try it live", "Real SVG" and "Campaign" run on the server, and the Nemotron option uses the demo's model budget. "Compare" shows stored results
          only. Not built in this prototype: a skill inspector, entering a corrected example after "Neither", and model-written SVG patches.
        </p>
      </footer>
    </div>
  );
}


type Area = "adapt" | "apprentice" | "prototype";

const areaFromHash = (): Area => {
  const h = window.location.hash;
  return h === "" || h.startsWith("#adapt") ? "adapt" : h.startsWith("#apprentice") ? "apprentice" : "prototype";
};

/** "Adapt a banner" is the front door; the diagram skill and the earlier prototype stay one click away. */
export function App() {
  const [area, setArea] = useState<Area>(areaFromHash());
  useEffect(() => {
    const onHash = () => setArea(areaFromHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  const pick = (a: Area) => {
    window.location.hash = a === "adapt" ? "adapt" : a === "apprentice" ? "apprentice" : "home";
    setArea(a);
  };
  return (
    <>
      <a
        className="skip"
        href="#stage"
        onClick={(e) => {
          // the hash router would treat "#stage" as a tab name; move focus instead
          e.preventDefault();
          const stage = document.getElementById("stage");
          if (stage) {
            if (!stage.hasAttribute("tabindex")) stage.setAttribute("tabindex", "-1");
            stage.focus();
          }
        }}
      >
        {area === "prototype" ? "Skip to the canvas" : "Skip to the content"}
      </a>
      <header className="shell">
        <div className="mark">
          <svg viewBox="0 0 32 32" aria-hidden="true" className="logo">
            <rect x="3" y="5" width="15" height="10" rx="2" />
            <rect x="14" y="19" width="15" height="9" rx="2" />
            <path d="M6 18h8M17 31h9" />
          </svg>
          <div>
            <h1 className="name">Open Apprentice</h1>
          </div>
        </div>
        <nav aria-label="Areas" className="areas">
          <ul className="tabs" role="tablist">
            <li role="presentation">
              <button role="tab" aria-selected={area === "adapt"} className={area === "adapt" ? "tab on" : "tab"} onClick={() => pick("adapt")}>
                Adapt a banner
              </button>
            </li>
            <li role="presentation">
              <button role="tab" aria-selected={area === "apprentice"} className={area === "apprentice" ? "tab on" : "tab"} onClick={() => pick("apprentice")}>
                Diagrams
              </button>
            </li>
            <li role="presentation">
              <button role="tab" aria-selected={area === "prototype"} className={area === "prototype" ? "tab on" : "tab"} onClick={() => pick("prototype")}>
                UI components · Earlier prototype
              </button>
            </li>
          </ul>
        </nav>
      </header>
      {area === "adapt" ? <Adapt /> : area === "apprentice" ? <Apprentice /> : <Prototype />}
    </>
  );
}
