import type { Attempt, Axes, Check, Program, Step, VersionRow } from "./types";

const AXIS_ROWS: { key: keyof Axes; title: string; asks: string }[] = [
  { key: "intent", title: "Intent", asks: "Is it settled what you meant?" },
  { key: "symbolic", title: "Symbolic", asks: "Does the rule hold within the stated model?" },
  { key: "native", title: "Native", asks: "Does the real backend do it?" },
  { key: "held_out", title: "Held-out", asks: "Does it hold on inputs it never saw?" },
];

type Tone = "ok" | "warn" | "bad" | "idle";

function toneOf(text: string): { tone: Tone; mark: string } {
  const t = text.toLowerCase();
  if (t.startsWith("not yet") || t.startsWith("not applicable")) return { tone: "idle", mark: "–" };
  if (t.includes("mismatch") || t.includes("ambiguous") || t.includes("untrusted")) return { tone: "bad", mark: "!" };
  if (t.includes("only") || t.includes("once") || t.includes("listed")) return { tone: "warn", mark: "~" };
  return { tone: "ok", mark: "✓" };
}

/** Four separate claims. There is deliberately no combined score or single "Verified" badge. */
export function AxisChips({ axes }: { axes: Axes }) {
  return (
    <section aria-label="Evidence on four separate questions" className="axes">
      <h3>Evidence, four separate questions</h3>
      <ul>
        {AXIS_ROWS.map((r) => {
          const { tone, mark } = toneOf(axes[r.key]);
          return (
            <li key={r.key} className={`axis tone-${tone}`}>
              <span className="axis-mark" aria-hidden="true">{mark}</span>
              <span className="axis-body">
                <span className="axis-title">{r.title}</span>
                <span className="axis-asks">{r.asks}</span>
                <span className="axis-value">{axes[r.key]}</span>
              </span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

export function Checks({ checks, passed }: { checks: Check[]; passed?: boolean }) {
  return (
    <section className="checks" aria-label="Independent verifier checks">
      <h3>
        Independent verifier <span className={passed ? "pill ok" : "pill bad"}>{passed ? "PASS" : "FAIL"}</span>
      </h3>
      <p className="muted">Recomputed from raw engine state without using the agent-facing measurement tool.</p>
      <ul>
        {checks.map((c) => (
          <li key={c.name} className={c.passed ? "ok-text" : "fail-text"}>
            <span aria-hidden="true">{c.passed ? "✓" : "✗"}</span> <span className="visually-hidden">{c.passed ? "Passed: " : "Failed: "}</span>
            {c.name.replace(/_/g, " ")}
            {!c.passed && c.detail ? <span className="muted"> — {c.detail}</span> : null}
          </li>
        ))}
      </ul>
    </section>
  );
}

export function Hash({ label, value }: { label: string; value: string }) {
  return (
    <div className="hash">
      <span className="hash-label">{label}</span>
      <code title={value}>{value.slice(0, 12)}…</code>
    </div>
  );
}

type Line = { kind: "same" | "add" | "del"; text: string };

/** Plain longest-common-subsequence line diff; programs are tiny. */
export function diffLines(a: string[], b: string[]): Line[] {
  const n = a.length;
  const m = b.length;
  const dp: number[][] = Array.from({ length: n + 1 }, () => new Array<number>(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
    }
  }
  const out: Line[] = [];
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (a[i] === b[j]) {
      out.push({ kind: "same", text: a[i] });
      i++;
      j++;
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      out.push({ kind: "del", text: a[i++] });
    } else {
      out.push({ kind: "add", text: b[j++] });
    }
  }
  while (i < n) out.push({ kind: "del", text: a[i++] });
  while (j < m) out.push({ kind: "add", text: b[j++] });
  return out;
}

const pretty = (p: Program): string[] => JSON.stringify(p, null, 1).split("\n");

export function ProgramDiff({ before, after }: { before: Program; after: Program }) {
  const lines = diffLines(pretty(before), pretty(after));
  const added = lines.filter((l) => l.kind === "add").length;
  const removed = lines.filter((l) => l.kind === "del").length;
  return (
    <section className="diff" aria-label="Native procedure, old versus new">
      <h3>Native procedure: what changed</h3>
      <p className="muted">
        {removed} lines removed, {added} lines added. The rule itself is not part of this program and is not touched.
      </p>
      <pre tabIndex={0}>
        {lines.map((l, i) => (
          <span key={i} className={`dl ${l.kind}`}>
            <span aria-hidden="true">{l.kind === "add" ? "+ " : l.kind === "del" ? "- " : "  "}</span>
            <span className="visually-hidden">{l.kind === "add" ? "added: " : l.kind === "del" ? "removed: " : ""}</span>
            {l.text}
          </span>
        ))}
      </pre>
    </section>
  );
}

export function VersionTable({ versions }: { versions: VersionRow[] }) {
  return (
    <table className="data">
      <caption>Binding versions (immutable; rollback only moves the active pointer)</caption>
      <thead>
        <tr><th>Version</th><th>Parent</th><th>Program hash</th><th>Status</th></tr>
      </thead>
      <tbody>
        {versions.map((v) => (
          <tr key={v.version}>
            <td>v{v.version}</td>
            <td>{v.parent === null ? "–" : `v${v.parent}`}</td>
            <td><code>{v.program_hash.slice(0, 12)}…</code></td>
            <td>{v.active ? "active" : "retained"}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

export function Facts({ step }: { step: Step }) {
  return (
    <div className="facts">
      {step.sealed_hash ? <Hash label="Sealed concept hash" value={step.sealed_hash} /> : null}
      {step.binding ? <Hash label={`Fabric binding v${step.binding.version} program`} value={step.binding.program_hash} /> : null}
      {step.binding ? <Hash label="Concept hash it carries" value={step.binding.concept_hash} /> : null}
      {step.concept_hash_before ? <Hash label="Concept hash before repair" value={step.concept_hash_before} /> : null}
      {step.concept_hash_after ? <Hash label="Concept hash after repair" value={step.concept_hash_after} /> : null}
    </div>
  );
}

export function Attempts({ attempts }: { attempts: Attempt[] }) {
  return (
    <section className="attempts" aria-label="Candidate repairs">
      <h3>Candidate repairs</h3>
      <ol>
        {attempts.map((a) => (
          <li key={a.candidate} className={a.failed_stage ? "fail-text" : "ok-text"}>
            <strong>{a.failed_stage ? "Rejected" : "Promoted"}</strong>
            {a.source ? <span className="muted"> ({a.source === "model" ? "model-generated" : "scripted fixture"})</span> : null}: {a.diagnosis || "scripted fixture patch"}
            {a.failed_stage ? <span> — failed at <code>{a.failed_stage.replace(/_/g, " ")}</code></span> : null}
            <ul className="cases">
              {a.cases.map((c, i) => (
                <li key={i} className={c.passed ? "ok-text" : "fail-text"}>
                  <span aria-hidden="true">{c.passed ? "✓" : "✗"}</span> {c.passed ? "passed" : "failed"}: {c.stage.replace(/_/g, " ")} ({c.native_actions} native actions)
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ol>
    </section>
  );
}
