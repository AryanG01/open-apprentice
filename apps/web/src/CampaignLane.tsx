import { useCallback, useEffect, useState } from "react";
import type { CampaignEngine, CampaignFixture, CampaignPreview, CampaignRun, CampaignScope, CampaignWorkspace } from "./types";

const OUTCOME_LABEL: Record<string, string> = {
  builtin_shrink_hero: "Shrink the product image",
  builtin_split_two_cards: "Split across two cards",
};
const outcomeLabel = (o: string): string => OUTCOME_LABEL[o] ?? o;

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

function PreviewCard({ p, busy, onPick }: { p: CampaignPreview; busy: boolean; onPick: (o: string) => void }) {
  return (
    <figure className={p.fits ? "preview" : "preview nofit"}>
      <img src={p.png} alt={`${outcomeLabel(p.outcome)} preview`} />
      <figcaption>
        <span className="pill recorded">built-in</span> <span className={p.fits ? "pill ok" : "pill bad"}>{p.fits ? "fits" : "does not fit"}</span>
        {p.violations.length ? (
          <ul className="muted small">
            {p.violations.slice(0, 4).map((v, i) => (
              <li key={i}>
                {v.kind.replace(/_/g, " ")}: {v.node_id}
              </li>
            ))}
          </ul>
        ) : null}
      </figcaption>
      <button className="btn primary" disabled={busy || !p.fits} onClick={() => onPick(p.outcome)} title={p.fits ? undefined : "This outcome does not fit this banner"}>
        {outcomeLabel(p.outcome)}
      </button>
    </figure>
  );
}

export function CampaignLane() {
  const [fixtures, setFixtures] = useState<CampaignFixture[]>([]);
  const [ws, setWs] = useState<CampaignWorkspace | null>(null);
  const [run, setRun] = useState<CampaignRun | null>(null);
  const [scopes, setScopes] = useState<CampaignScope[]>([]);
  const [engine, setEngine] = useState<CampaignEngine>("konva");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    call<{ fixtures: CampaignFixture[] }>("/api/campaign/fixtures")
      .then((r) => setFixtures(r.fixtures))
      .catch((e: Error) => setError(`The Campaign lane needs the backend (${e.message}).`));
  }, []);

  const go = useCallback(async (fn: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }, []);

  const refreshPrefs = async (wid: string) => setScopes((await call<{ scopes: CampaignScope[] }>(`/api/campaign/workspaces/${wid}/preferences`)).scopes);

  const learn = () =>
    go(async () => {
      const w = await call<CampaignWorkspace>("/api/campaign/workspaces", {});
      setWs(w);
      setRun(null);
      await refreshPrefs(w.workspace_id);
    });

  const start = (fid: string) =>
    go(async () => {
      if (!ws) return;
      setRun(await call<CampaignRun>(`/api/campaign/workspaces/${ws.workspace_id}/runs`, { fixture_id: fid, backend: engine }));
      await refreshPrefs(ws.workspace_id);
    });

  const reply = (choice: string) =>
    go(async () => {
      if (!ws || !run) return;
      const active = scopes.find((s) => s.locale === run.locale)?.active ?? null;
      setRun(await call<CampaignRun>(`/api/campaign/workspaces/${ws.workspace_id}/runs/${run.run_id}/answer`, { choice, expected_version: active ? active.version : null }));
      await refreshPrefs(ws.workspace_id);
    });

  const rollback = (s: CampaignScope, to: number) =>
    go(async () => {
      if (!ws || !s.active) return;
      await call<CampaignScope>(`/api/campaign/workspaces/${ws.workspace_id}/preferences/rollback`, { locale: s.locale, to_version: to, expected_version: s.active.version });
      await refreshPrefs(ws.workspace_id);
    });

  const teaching = fixtures.find((f) => f.kind === "teaching");
  const verification = run?.result?.verification ?? null;
  const passedCount = verification ? verification.checks.filter((c) => c.passed).length : 0;

  return (
    <main className="page campaign" id="stage">
      <p className="eyebrow">Campaign lane · development fixtures, not held out</p>
      <h2>Banner to story card, taught once</h2>
      <p className="lede">
        One example teaches the layout. When a banner's copy does not fit, the apprentice stops and shows two built-in outcomes, already applied. Every result it applies passes the
        independent verifier first.
      </p>
      {error ? (
        <p className="callout bad" role="alert">
          {error}
        </p>
      ) : null}

      <section aria-labelledby="c-teach">
        <h3 id="c-teach">1. Teaching example</h3>
        <div className="svgpair">
          <figure>
            {ws ? <img src={ws.teaching.before_png} alt="Banner before" /> : teaching ? <img src={teaching.png} alt="Banner before" /> : null}
            <figcaption>Before: 16:9 banner</figcaption>
          </figure>
          <figure>
            {ws ? <img src={ws.teaching.after_png} alt="Story card after" /> : <div className="placeholder">Learn to see the taught story card</div>}
            <figcaption>After: 1080 × 1920 story card</figcaption>
          </figure>
        </div>
        <div className="controls">
          <button className="btn primary" onClick={learn} disabled={busy || !fixtures.length}>
            Learn this layout
          </button>
          {ws ? (
            <span>
              Learned by <span className="pill ok">{ws.learned.origin}</span>{" "}
              <span className="muted small">
                {ws.learned.candidates.length} candidate{ws.learned.candidates.length === 1 ? "" : "s"} checked against the example
              </span>
            </span>
          ) : null}
        </div>
      </section>

      <section aria-labelledby="c-run">
        <h3 id="c-run">2. Run on a banner</h3>
        <fieldset className="controls" disabled={busy}>
          <legend className="muted small">Graphics engine (same learned rule on both)</legend>
          {(["konva", "fabric"] as const).map((e) => (
            <label key={e}>
              <input type="radio" name="campaign-engine" value={e} checked={engine === e} onChange={() => setEngine(e)} /> {e === "konva" ? "Konva" : "Fabric"}
            </label>
          ))}
        </fieldset>
        <div className="samples">
          {fixtures
            .filter((f) => f.kind !== "teaching")
            .map((f) => (
              <button key={f.id} className={run?.fixture_id === f.id ? "samplebtn on" : "samplebtn"} disabled={busy || !ws} onClick={() => start(f.id)}>
                <img src={f.png} alt="" className="thumb" />
                <strong>{f.id}</strong>
                <span className="muted small">
                  {f.locale}
                  {f.kind === "broken" ? " · broken on purpose" : ""}
                </span>
              </button>
            ))}
        </div>

        {run ? (
          <div className="runout" aria-live="polite">
            <p>
              <strong>{run.fixture_id}</strong>: <span className={run.status === "ready" || run.status === "applied" ? "pill ok" : run.status === "question" ? "pill live" : "pill bad"}>{run.status}</span>{" "}
              <span className="pill recorded">engine: {run.backend}</span> <span className="pill recorded">learned: {String(run.provenance.learned_origin ?? "")}</span>{" "}
              <span className="pill recorded">procedure: {String(run.provenance.procedure_origin ?? "")}</span>
              {run.provenance.outcome_origin ? <span className="pill recorded"> outcome: built-in</span> : null}
              {run.status === "applied" && run.previews.length === 0 && run.provenance.preference_version ? (
                <span className="pill live"> Saved preference: {outcomeLabel(run.preference?.outcome ?? "")} v{String(run.provenance.preference_version)}</span>
              ) : null}
            </p>
            {run.problems.length || run.status === "blocked" ? (
              <div className="callout bad" role="alert">
                {run.status === "blocked" ? <p>Not applied: the independent verifier refused this result ({verification?.failed.join(", ")}).</p> : null}
                {run.problems.map((p) => (
                  <p key={p}>{p}</p>
                ))}
              </div>
            ) : null}
            {run.result ? (
              <div className="svgpair">
                <figure>
                  <img src={run.result.png} alt={`${run.fixture_id} result`} />
                  <figcaption>{run.status === "blocked" ? "Refused result (not applied)" : "Applied result"}</figcaption>
                </figure>
                {verification ? (
                  <div>
                    <p>
                      <strong>
                        {passedCount} of {verification.checks.length} checks passed
                      </strong>{" "}
                      <span className="muted small">independent verifier, against the authored expected output</span>
                    </p>
                    <div className="table-wrap">
                      <table className="data">
                        <tbody>
                          {verification.checks.map((c) => (
                            <tr key={c.name}>
                              <td>{c.name.replace(/_/g, " ")}</td>
                              <td>{c.passed ? <span className="pill ok">pass</span> : <span className="pill bad">fail</span>}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                ) : null}
              </div>
            ) : null}
            {run.status === "question" ? (
              <div className="question">
                <p className="q">Which tradeoff should this rule make when the offer does not fit?</p>
                <div className="svgpair two">
                  {run.previews.map((p) => (
                    <PreviewCard key={p.outcome} p={p} busy={busy} onPick={reply} />
                  ))}
                </div>
                <button className="btn" disabled={busy} onClick={() => reply("neither")}>
                  Neither (leave unchanged)
                </button>
                <p className="muted small">Your answer is saved as a preference for {run.locale} banners; another language asks again.</p>
              </div>
            ) : null}
            {run.status === "unchanged" ? <p className="muted">Left unchanged. Nothing was saved.</p> : null}
          </div>
        ) : null}
      </section>

      {ws ? (
        <section aria-labelledby="c-prefs">
          <h3 id="c-prefs">3. Saved preferences</h3>
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>Language</th>
                  <th>Active</th>
                  <th>History</th>
                </tr>
              </thead>
              <tbody>
                {scopes.map((s) => (
                  <tr key={s.scope}>
                    <td>{s.locale}</td>
                    <td>{s.active ? `${outcomeLabel(s.active.outcome)} (v${s.active.version})` : <span className="muted">none: asks</span>}</td>
                    <td>
                      {s.history.map((h) => (
                        <span key={h.version} className="hist">
                          v{h.version} {outcomeLabel(h.outcome)}
                          {s.active && h.version !== s.active.version ? (
                            <button className="btn small" disabled={busy} onClick={() => rollback(s, h.version)}>
                              Roll back to v{h.version}
                            </button>
                          ) : null}
                        </span>
                      ))}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}
    </main>
  );
}
