import type { ThinkingStep } from "./types";

/** Colours of the alternatives a question shows (A, B, C, D); shared with the question cards. */
export const ALT_COLOURS: Record<string, string> = { A: "var(--alt-a)", B: "var(--alt-b)", C: "var(--alt-c)", D: "var(--alt-d)" };

const ROUND_TEXT: Record<string, string> = {
  initial: "First guesses",
  revision: "Second try after none fitted",
  contrastive: "Looked for rules that disagree",
};

/** How many rules still fit at this point of the trace. */
function standing(t: ThinkingStep[]): number | null {
  for (let i = t.length - 1; i >= 0; i--) {
    const s = t[i];
    if (s.kind === "round" || s.kind === "answer") return s.survivors;
    if (s.kind === "question") return s.candidates;
    if (s.kind === "commit") return 1;
  }
  return null;
}

/** The apprentice's notebook: what it proposed, what survived your example, the test diagrams it drew and why it asked. */
export function Thinking({ steps, working }: { steps: ThinkingStep[]; working: boolean }) {
  const n = standing(steps);
  const proposed = steps.reduce((k, s) => (s.kind === "round" ? k + s.proposed : k), 0);
  const source = steps.find((s): s is Extract<ThinkingStep, { kind: "round" }> => s.kind === "round")?.source;
  return (
    <aside className="notebook" aria-label="What the apprentice is thinking">
      <div className="counter" aria-live="polite">
        <span className="num" data-count={n ?? ""}>{n ?? "…"}</span>
        <span className="cap">
          {n === null ? "reading your example" : n === 1 ? "rule fits everything you showed" : "rules fit your example"}
          {proposed ? <small>{proposed} considered{source ? `, proposed by the ${source}` : ""}</small> : null}
        </span>
      </div>
      <ol className="trace">
        {steps.map((s, i) => (
          <li key={i} className={`t-${s.kind}`}>
            {s.kind === "round" ? (
              <>
                <b>{ROUND_TEXT[s.round_kind] ?? s.round_kind}</b>: {s.proposed} proposed, {s.survivors} fit
                {s.truncated ? " (the reply was cut off and counted as an empty round)" : ""}
                {s.summaries.length ? (
                  <ul className="rules">
                    {s.summaries.map((r, k) => (
                      <li key={k}>{r}</li>
                    ))}
                  </ul>
                ) : null}
              </>
            ) : s.kind === "probe" ? (
              <>
                <b>Drew a test diagram</b> {s.ok ? "where the rules would disagree" : "but it did not render as planned, so it was not used"}
              </>
            ) : s.kind === "question" ? (
              <>
                <b>Asked you</b>: here the {s.candidates} rules that fit give {Object.keys(s.groups).length} different results
                <ul className="groups">
                  {Object.entries(s.groups).map(([alt, rules]) => (
                    <li key={alt} style={{ borderColor: ALT_COLOURS[alt] }}>
                      <span className="alt" style={{ background: ALT_COLOURS[alt] }}>{alt}</span> {rules.join(" / ") || "—"}
                    </li>
                  ))}
                </ul>
              </>
            ) : s.kind === "preview" ? (
              <>
                <b>Showed a preview</b> on {s.items} other document{s.items === 1 ? "" : "s"}
              </>
            ) : s.kind === "answer" ? (
              <>
                <b>Your answer</b> left {s.survivors} rule{s.survivors === 1 ? "" : "s"}
              </>
            ) : s.kind === "commit" ? (
              <>
                <b>Kept as a skill:</b> {s.summary}
              </>
            ) : (
              <>
                <b>Stopped:</b> {s.reason}
              </>
            )}
          </li>
        ))}
        {working ? <li className="t-working">Thinking…</li> : null}
      </ol>
    </aside>
  );
}
