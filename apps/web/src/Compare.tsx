import type { Evidence, MethodRow } from "./types";

const METHOD_LABEL: Record<string, string> = {
  enumerative_reference: "Non-model reference",
  full_v1_2: "Open Apprentice (full)",
  fresh_full_context: "Fresh agent, full context",
  text_memory: "Text memory",
  structured_procedure: "Structured procedure",
};

const ORDER = ["enumerative_reference", "full_v1_2", "structured_procedure", "text_memory", "fresh_full_context"];

function Failures({ row }: { row: MethodRow }) {
  const entries = Object.entries(row.failures);
  if (entries.length === 0) return <span className="muted">none recorded</span>;
  return <>{entries.map(([k, v]) => `${k.replace(/_/g, " ")} ×${v}`).join(", ")}</>;
}

export function Compare({ data }: { data: Evidence }) {
  return (
    <div className="compare">
      <div className="callout" role="note">
        <strong>Read this first.</strong> These are stored development-split pilot runs with a handful of episodes. They show where the system
        fails today, not that one method beats another. No quality gate from the spec is evaluated on them.
      </div>

      <h2>Recorded live runs</h2>
      <p className="muted">
        Generated {data.generated_at.slice(0, 16).replace("T", " ")} UTC by counting stored rows (the same rows <code>oa report</code> reads).
      </p>
      {data.runs.map((run) => (
        <section key={run.run} className="run-card" aria-label={`Run ${run.run}`}>
          <h3>
            <span className="pill live">LIVE MODEL</span> {run.run}
          </h3>
          <p className="muted">{run.label}; {run.episodes} episode{run.episodes === 1 ? "" : "s"}</p>
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr><th>Method</th><th>Correct</th><th>Committed but wrong</th><th>Abstained</th><th>Model tokens</th><th>Why it did not finish</th></tr>
              </thead>
              <tbody>
                {ORDER.filter((m) => run.methods[m]).map((m) => {
                  const r = run.methods[m];
                  return (
                    <tr key={m}>
                      <th scope="row">{METHOD_LABEL[m] ?? m}</th>
                      <td>{r.correct} of {r.scheduled}</td>
                      <td className={r.committed_wrong > 0 ? "fail-text" : ""}>{r.committed_wrong}</td>
                      <td>{r.abstained}</td>
                      <td>{r.tokens === 0 ? "0 (no model)" : r.tokens.toLocaleString()}</td>
                      <td><Failures row={r} /></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </section>
      ))}

      <h2>Can the model learn the rule from a demonstration?</h2>
      <p className="muted">Teaching trials on the development split: rule recovered on unseen scenes, hidden from the model.</p>
      <div className="trials">
        {data.teaching_trials.map((t) => (
          <section key={t.concept} className="trial-card" aria-label={`${t.concept} teaching trials`}>
            <h3>{t.concept === "badge" ? "Badge placement" : "Row spacing"}</h3>
            <p className="big">{t.recovered}<span> of {t.trials} recovered</span></p>
            <div className="bar" role="img" aria-label={`${t.recovered} recovered, ${t.ready_but_wrong} confident but wrong, ${t.unresolved} unresolved, out of ${t.trials}`}>
              <span className="seg ok" style={{ flexGrow: t.recovered }} />
              <span className="seg bad" style={{ flexGrow: t.ready_but_wrong }} />
              <span className="seg idle" style={{ flexGrow: t.unresolved }} />
            </div>
            <ul className="legend">
              <li><span className="swatch ok" /> recovered: {t.recovered}</li>
              <li><span className="swatch bad" /> confident but wrong: {t.ready_but_wrong}</li>
              <li><span className="swatch idle" /> unresolved: {t.unresolved}</li>
            </ul>
            <p className="muted">{t.model.split("/").pop()}, reasoning effort {t.reasoning_effort}</p>
          </section>
        ))}
      </div>

      {data.experiments && data.experiments.length > 0 ? (
        <>
          <h2>What reduces the wrong commits? Three arms on the same development episodes</h2>
          <p className="muted">
            Same 12 development episodes and both concepts. The audit arm adds one model round hunting for other rules: <strong>it did not help</strong>, it just made the system silent. The hybrid arm
            unions the model's rules with a bounded symbolic search: <strong>wrong commits fell sharply</strong>. Caveats: the hybrid arm has one repetition (24 trials) against two (48) for the others, and a
            non-model search alone also solves these tasks, so this does not show that the model adds value.
          </p>
          <div className="table-wrap">
            <table className="data">
              <thead><tr><th>Arm</th><th>Trials</th><th>Committed</th><th>Correct</th><th>Wrong</th><th>Wrong share of committed</th><th>Abstained</th><th>Lost to errors</th><th>Tokens</th></tr></thead>
              <tbody>
                {data.experiments.map((e) => (
                  <tr key={e.arm}>
                    <th scope="row">{e.arm}</th>
                    <td>{e.trials}</td>
                    <td>{e.committed}</td>
                    <td>{e.correct}</td>
                    <td className={e.wrong > 0 ? "fail-text" : ""}>{e.wrong}</td>
                    <td>{e.wrong_share_of_committed === null ? "–" : `${Math.round(e.wrong_share_of_committed * 100)}%`}</td>
                    <td>{e.abstained}</td>
                    <td>{e.errors}</td>
                    <td>{e.tokens.toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : null}

      <h2>Limits of this evidence</h2>
      <ul className="caveats">
        {data.caveats.map((c) => (
          <li key={c}>{c}</li>
        ))}
        <li>The non-model reference solves every task, which shows the tasks and the independent verifier are sound.</li>
        <li>The model methods mostly abstain: they could not settle on the rule, or could not write a working native procedure, so they declined to commit.</li>
      </ul>
    </div>
  );
}
