import { useEffect, useState } from "react";
import type { SvgApply, SvgHarm, SvgInspect, SvgPair, SvgSample } from "./types";

const dataUrl = (svg: string): string => `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
const short = (h: string): string => `${h.slice(0, 10)}…`;
const r1 = (n: number): number => Math.round(n * 10) / 10;

async function call<T>(path: string, body?: object): Promise<T> {
  const res = await fetch(path, { method: body ? "POST" : "GET", headers: body ? { "Content-Type": "application/json" } : undefined, body: body ? JSON.stringify(body) : undefined });
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const j = (await res.json()) as { detail?: unknown };
      if (typeof j.detail === "string") detail = j.detail;
      else if (j.detail && typeof j.detail === "object") detail = JSON.stringify(j.detail);
    } catch {
      /* keep the status */
    }
    throw new Error(detail);
  }
  return (await res.json()) as T;
}

function download(name: string, text: string, type: string): void {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

function readSession(): string | null {
  try {
    return window.sessionStorage.getItem("oa.session");
  } catch {
    return null;
  }
}

export function SvgLane({ go }: { go: (hash: string) => void }) {
  const [samples, setSamples] = useState<SvgSample[]>([]);
  const [rule, setRule] = useState<{ id: string; text: string } | null>(null);
  const [src, setSrc] = useState<{ sample?: string; svg?: string; label: string } | null>(null);
  const [info, setInfo] = useState<SvgInspect | null>(null);
  const [pairs, setPairs] = useState<SvgPair[]>([]);
  const [result, setResult] = useState<SvgApply | null>(null);
  const [harm, setHarm] = useState<SvgHarm | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    call<SvgSample[]>("/api/svg/samples").then(setSamples).catch((e: Error) => setError(`The SVG lane needs the backend (${e.message}).`));
    const sid = readSession();
    if (sid) {
      call<{ concept?: { rule_text: string } }>(`/api/teach/${sid}`)
        .then((s) => setRule(s.concept ? { id: sid, text: s.concept.rule_text } : null))
        .catch(() => setRule(null));
    }
  }, []);

  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
    } finally {
      setBusy(false);
    }
  };

  const choose = (s: { sample?: string; svg?: string; label: string }) =>
    run(async () => {
      setResult(null);
      setHarm(null);
      const r = await call<SvgInspect>("/api/svg/inspect", s.sample ? { sample: s.sample } : { svg: s.svg });
      setSrc(s);
      setInfo(r);
      setPairs(r.suggested_pairs);
    });

  const editable = info?.inventory.elements.filter((e) => e.editable) ?? [];
  const body = src ? (src.sample ? { sample: src.sample } : { svg: src.svg }) : {};

  const apply = () =>
    run(async () => {
      if (!rule) return;
      setResult(await call<SvgApply>("/api/svg/apply", { ...body, session_id: rule.id, pairs }));
    });

  const tryHarm = () =>
    run(async () => {
      setHarm(await call<SvgHarm>("/api/svg/harmful-demo", body));
    });

  return (
    <main className="page svglane" id="stage">
      <p className="eyebrow">Experimental lane · no language model</p>
      <h2>Apply what you taught to a real SVG document</h2>
      <p className="lede">
        The original file stays the authority. The rule you taught moves an existing badge element by a typed, whitelisted patch to its <code>x</code> and <code>y</code>; nothing is inserted or deleted.
        The result is measured in a locked browser with native SVG geometry, and the export differs from your file only in the patched attributes.
      </p>
      {error ? <p className="callout bad" role="alert">{error}</p> : null}

      <section className="callout" role="note" aria-label="Rule to apply">
        {rule ? (
          <>
            <strong>Rule to apply:</strong> {rule.text}
          </>
        ) : (
          <>
            <strong>No taught rule yet.</strong> This lane applies the rule you taught in <em>Try it live</em>.{" "}
            <button className="btn" onClick={() => go("live")}>Go teach one</button>
          </>
        )}
      </section>

      <h3>1. Choose an owner-authored document</h3>
      <div className="samples">
        {samples.map((s) => (
          <button key={s.id} className={src?.sample === s.id ? "samplebtn on" : "samplebtn"} onClick={() => choose({ sample: s.id, label: s.id })} disabled={busy}>
            <strong>{s.id}</strong>
            <span className="muted small">{s.coverage.editable} of {s.coverage.listed} elements editable · {s.bytes} bytes</span>
          </button>
        ))}
        <label className="btn filebtn">
          Check your own SVG…
          <input
            type="file"
            accept="image/svg+xml,.svg"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void f.text().then((t) => choose({ svg: t, label: f.name }));
              e.target.value = "";
            }}
          />
        </label>
      </div>
      <p className="muted small">Only documents with clear provenance (yours, or independently verified). Scripts, external references, styles, images, entities and anything it cannot edit safely are rejected with a reason, never silently cleaned.</p>

      {info && src ? (
        <>
          <h3>2. Public inventory</h3>
          <div className="svgpair">
            <figure>
              <img src={dataUrl(info.source)} alt={`Rendered preview of ${src.label}`} />
              <figcaption>{src.label} · document hash <code title={info.inventory.hash}>{short(info.inventory.hash)}</code></figcaption>
            </figure>
            <div className="table-wrap">
              <table className="data">
                <caption>{info.inventory.coverage.editable} of {info.inventory.coverage.listed} listed elements are editable; {info.inventory.inert_vector_elements} inert vector shapes are left alone</caption>
                <thead><tr><th>Element</th><th>Kind</th><th>World box (x, y, w × h)</th><th>Editable</th></tr></thead>
                <tbody>
                  {info.inventory.elements.map((e) => (
                    <tr key={e.id}>
                      <th scope="row">{e.id}</th>
                      <td>{e.tag}</td>
                      <td>{e.world ? `${r1(e.world.x)}, ${r1(e.world.y)}, ${r1(e.world.width)} × ${r1(e.world.height)}` : "–"}</td>
                      <td className={e.editable ? "ok-text" : "muted"}>{e.editable ? "yes" : `no: ${e.reason ?? ""}`}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <h3>3. Which badge belongs to which card?</h3>
          <ul className="pairs">
            {pairs.map((p, i) => (
              <li key={i}>
                <label>Card
                  <select value={p.card} onChange={(e) => setPairs(pairs.map((q, j) => (j === i ? { ...q, card: e.target.value } : q)))}>
                    {editable.map((e) => <option key={e.id} value={e.id}>{e.id}</option>)}
                  </select>
                </label>
                <label>Badge
                  <select value={p.badge} onChange={(e) => setPairs(pairs.map((q, j) => (j === i ? { ...q, badge: e.target.value } : q)))}>
                    {editable.map((e) => <option key={e.id} value={e.id}>{e.id}</option>)}
                  </select>
                </label>
                <button onClick={() => setPairs(pairs.filter((_, j) => j !== i))} aria-label={`Remove pair ${i + 1}`}>Remove</button>
              </li>
            ))}
          </ul>
          <div className="controls">
            <button onClick={() => setPairs([...pairs, { card: editable[0]?.id ?? "", badge: editable[1]?.id ?? "" }])} disabled={editable.length < 2}>Add a pair</button>
            <button onClick={() => setPairs(info.suggested_pairs)}>Use suggested pairs</button>
            <button className="primary" onClick={apply} disabled={busy || !rule || pairs.length === 0}>Apply the rule</button>
            <button onClick={tryHarm} disabled={busy}>Try harmful patches</button>
          </div>
        </>
      ) : null}

      {harm ? (
        <section className={harm.all_rejected ? "callout ok" : "callout bad"} role="note" aria-label="Harmful patch attempts">
          <strong>{harm.all_rejected ? "Every harmful patch was rejected." : "A harmful patch was ACCEPTED. This is a bug."}</strong>
          <ul className="replay">
            {harm.attempts.map((a) => (
              <li key={a.attempt} className={a.rejected ? "ok-text" : "fail-text"}>
                <span aria-hidden="true">{a.rejected ? "✓" : "✗"}</span> {a.attempt} <span className="muted">({a.rejected ? a.reasons.join("; ") : "accepted"})</span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {result ? (
        <>
          <h3>4. Result</h3>
          <p className={result.passed ? "callout ok" : "callout bad"} role="status">
            <strong>{result.passed ? "Verified in the browser." : "Verification FAILED."}</strong> The browser measured every badge where the rule puts it (within 0.5 px), and
            {result.only_selected_badges_moved ? " nothing else moved." : " something other than the selected badges moved."} Unrelated byte changes: <strong>{result.unrelated_byte_changes}</strong>.
            <span className="muted"> {result.scope}</span>
          </p>
          <div className="svgpair two">
            <figure><img src={dataUrl(result.original_svg)} alt="Original document" /><figcaption>Before · <code>{short(result.hash_before)}</code></figcaption></figure>
            <figure><img src={dataUrl(result.modified_svg)} alt="Document after the patch" /><figcaption>After · <code>{short(result.hash_after)}</code></figcaption></figure>
          </div>
          <div className="table-wrap">
            <table className="data">
              <caption>The exact patch (the only edits made)</caption>
              <thead><tr><th>Element</th><th>Attribute</th><th>Old</th><th>New</th></tr></thead>
              <tbody>
                {result.diff.map((d, i) => (
                  <tr key={i}><th scope="row">{d.element}</th><td>{d.attribute}</td><td>{d.old ?? "(absent)"}</td><td>{d.new}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="table-wrap">
            <table className="data">
              <caption>Measured in Chromium (world coordinates) against what the rule requires</caption>
              <thead><tr><th>Badge</th><th>Card</th><th>Rule requires (x, y)</th><th>Browser measured (x, y)</th><th>Error</th><th>Result</th></tr></thead>
              <tbody>
                {result.rows.map((row) => (
                  <tr key={row.badge}>
                    <th scope="row">{row.badge}</th><td>{row.card}</td>
                    <td>{r1(row.expected.x)}, {r1(row.expected.y)}</td>
                    <td>{row.measured ? `${r1(row.measured.x)}, ${r1(row.measured.y)}` : "–"}</td>
                    <td>{row.max_error_px === null ? "–" : `${row.max_error_px.toFixed(3)} px`}</td>
                    <td className={row.passed ? "ok-text" : "fail-text"}>{row.passed ? "PASS" : "FAIL"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="controls">
            <button className="btn primary" onClick={() => download(`${src?.label ?? "document"}-edited.svg`.replace(/\.svg-edited/, "-edited"), result.modified_svg, "image/svg+xml")}>Download the edited SVG</button>
            <button className="btn" onClick={() => download("patch.json", JSON.stringify(result.patch, null, 2), "application/json")}>Download the patch (JSON)</button>
          </div>
          <p className="muted small">Concept hash carried: <code title={result.concept_hash}>{short(result.concept_hash)}</code>. Not covered: arbitrary SVG paths, rotated or scaled elements, shared styles, and any claim of universal visual equivalence.</p>
        </>
      ) : null}
    </main>
  );
}
