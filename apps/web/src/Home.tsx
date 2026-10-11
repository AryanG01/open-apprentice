import type { Evidence } from "./types";

interface HomeProps {
  data: Evidence;
  go: (hash: string) => void;
}

function pct(n: number | null): string {
  return n === null ? "–" : `${Math.round(n * 100)}%`;
}

export function Home({ data, go }: HomeProps) {
  const control = data.experiments?.find((e) => e.variant === "control");
  const audit = data.experiments?.find((e) => e.variant === "audit");
  return (
    <main className="page home" id="stage">
      <section className="hero">
        <p className="eyebrow">Nebius × NVIDIA hackathon</p>
        <h2>Teach an agent a layout rule once. Trust it only as far as it can prove.</h2>
        <p className="lede">
          Show one example. When several rules fit it, Open Apprentice finds an input where they disagree, draws each outcome, and asks you. The rule you pick is sealed with a
          hash, carried to a second graphics engine, and, when the tool underneath changes silently, only the native procedure is repaired. Your rule never changes.
        </p>
        <div className="cta">
          <button className="btn primary" onClick={() => go("live")}>Try it live</button>
          <button className="btn" onClick={() => go("learn")}>Watch the recorded story</button>
          <button className="btn" onClick={() => go("compare")}>See the evidence</button>
        </div>
      </section>

      <section className="pillars" aria-label="What is different">
        <article>
          <h3>It asks only when it must</h3>
          <p>A solver finds the input where candidate rules disagree most, and the teacher answers by picture. “Neither” is always an option and never forced into a pick.</p>
        </article>
        <article>
          <h3>The rule survives a changing tool</h3>
          <p>Concept and native procedure are separate. A silent tool change is reproduced with real numbers; the repair is checked against earlier cases, and the sealed rule hash stays byte-identical.</p>
        </article>
        <article>
          <h3>Don't trust us. Re-check it.</h3>
          <p>Every layout ships with an evidence package. Re-derive its hashes and geometry offline, with no engine and no model. Edit one byte and the check fails.</p>
        </article>
      </section>

      <section className="honest" aria-label="What we measured">
        <h3>What we measured, including what did not work</h3>
        <ul>
          <li>
            Open-model teaching on development episodes: of the rules the model committed to, <strong>{control ? `${control.wrong} of ${control.committed} (${pct(control.wrong_share_of_committed)})` : "many"} were wrong</strong>,
            even after asking the teacher questions.
          </li>
          <li>
            One extra model round to hunt for alternatives did <strong>not</strong> fix it: {audit ? `${audit.wrong} of ${audit.committed} committed rules were still wrong (${pct(audit.wrong_share_of_committed)}), and the system went silent on ${audit.abstained} of ${audit.trials} trials` : "see Compare"}.
          </li>
          <li>A non-model reference solves every development task, so the tasks and the independent verifier are sound. Its grammar was built knowing the rule families, so we do not call that “understanding”.</li>
        </ul>
        <p className="muted">Development-split pilots, small samples, stored rows. Nothing here is the locked study.</p>
        <button className="btn" onClick={() => go("compare")}>Open the full comparison</button>
      </section>
    </main>
  );
}
