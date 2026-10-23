import type { Reasoning } from "./types";

const count = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

/** "Show the work" for the Try-it lane: how the question was chosen and what the solver did. Read-only; split sizes are
 * shown without saying which rule predicts which option, so they cannot steer the answer. */
export function TryItWork({ r }: { r: Reasoning }) {
  const sel = r.selection;
  const searches = sel?.witness_searches ?? [];
  const found = searches.filter((w) => w.status === "witness_found").length;
  const equal = searches.filter((w) => w.status === "no_witness_in_model").length;
  const other = searches.length - found - equal;
  const ms = searches.reduce((t, w) => t + w.elapsed_ms, 0);
  const version = searches[0]?.solver_version ?? r.settle?.solver_version;
  return (
    <details className="work" open aria-label="Show the work">
      <summary>Show the work</summary>
      <ol>
        <li>
          <strong>{count(r.candidate_count, "candidate rule")}</strong> still reproduce everything you have shown
          {r.rejected_count ? ` (${r.rejected_count} more were proposed and rejected for contradicting it)` : ""}.
        </li>
        {searches.length ? (
          <li>
            <strong>Z3{version ? ` ${version}` : ""}</strong> compared {count(searches.length, "pair")} of them: for {found} it found a concrete
            input where the two disagree{equal ? `, ${equal} proved to agree everywhere in the encoded domain` : ""}
            {other ? `, ${other} could not be decided within budget (never counted as agreement)` : ""}, in {Math.round(ms)} ms. Every witness is
            re-run concretely before use.
          </li>
        ) : null}
        {sel ? (
          <li>
            Of {count(sel.scenes_considered, "candidate input")}, this one splits the rules <strong>{sel.split.join(" / ")}</strong>: {sel.entropy_bits} bits
            of disagreement over {count(sel.cost_units, "object")} to look at (score {sel.score}). It is{" "}
            {sel.source === "solver_witness" ? "the solver's witness" : "a readable sampled input that splits them as much as the solver's witnesses"}.
            Your answer keeps only the rules that predicted it.
          </li>
        ) : null}
        {r.settle ? (
          <li>
            Final check: Z3 {r.settle.status === "no_witness_in_model"
              ? "found no input where the remaining rules differ, within the encoded domain (not a proof of what you meant)."
              : `could not rule out a difference (status ${r.settle.status.replace(/_/g, " ")}), so it does not commit.`}
          </li>
        ) : null}
      </ol>
      <p className="muted">
        Solver budget used: {r.solver.calls} of {r.solver.max_calls} calls, {r.solver.elapsed_s} s. Method: candidates kept consistent with all
        teaching (a version space); the question is the input they disagree on most (query by committee); witnesses come from Z3.
      </p>
    </details>
  );
}
