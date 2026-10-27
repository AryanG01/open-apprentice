import { useState } from "react";
import { DownloadSimple, ShieldCheck, WarningCircle } from "@phosphor-icons/react";
import { call } from "./CampaignLane";

interface SelfTest {
  mutation: string;
  label: string;
  caught: boolean;
  failed: string[];
}

const MUTATIONS = [
  ["delete_product", "Delete the product picture"],
  ["change_price", "Change a digit of the price"],
  ["push_headline_out", "Push the headline off the card"],
] as const;

const NICE: Record<string, string> = {
  source_complete: "a part from your banner is missing",
  exact_copy: "the words are no longer your approved words",
  inside_safe: "a part is outside the safe area",
  copy_once: "the words are not there exactly once",
  text_fits: "the text does not fit",
};

/** The proof moment: a record you can check without trusting the app, and a button that tries to break the finished result. */
export function ProofPanel({ wid, runId, pageCheck }: { wid: string; runId: string; pageCheck: unknown }) {
  const [tests, setTests] = useState<SelfTest[]>([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const base = `/api/campaign/workspaces/${wid}/runs/${runId}`;
  const download = async () => {
    setBusy(true);
    setErr("");
    try {
      const receipt = await call<object>(`${base}/receipt`, { page_check: pageCheck ?? null });
      const url = URL.createObjectURL(new Blob([JSON.stringify(receipt, null, 2)], { type: "application/json" }));
      const a = document.createElement("a");
      a.href = url;
      a.download = "open-apprentice-receipt.json";
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const tryBreak = async (m: string) => {
    setBusy(true);
    setErr("");
    try {
      const r = await call<SelfTest>(`${base}/selftest`, { mutation: m });
      setTests((t) => [r, ...t.filter((x) => x.mutation !== m)]);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="proof" aria-labelledby="proof-h">
      <h3 id="proof-h">
        <ShieldCheck size={20} weight="fill" aria-hidden="true" /> Proof you can check
      </h3>
      <p className="muted small">
        The receipt lists your approved words, link and pictures next to what ended up on the card, the checks that ran and the choice you made, tied to the
        files by hash. It shows the record matches the files; it does not show the card looks good.
      </p>
      <div className="row">
        <button type="button" className="btn" onClick={() => void download()} disabled={busy}>
          <DownloadSimple size={18} aria-hidden="true" /> Download the change receipt (JSON)
        </button>
      </div>
      <p className="muted small">
        Check it without the app: <code>python3 scripts/verify_receipt.py open-apprentice-receipt.json story-card.png</code> (script in the repository, standard library only).
      </p>
      <h4>Try to break it</h4>
      <p className="muted small">Each button damages a copy of this result and asks the independent checker whether it notices. Your result is not changed.</p>
      <div className="row">
        {MUTATIONS.map(([id, label]) => (
          <button key={id} type="button" className="btn" onClick={() => void tryBreak(id)} disabled={busy}>
            {label}
          </button>
        ))}
      </div>
      {err ? (
        <p className="callout bad" role="alert">
          {err}
        </p>
      ) : null}
      {tests.length ? (
        <ul className="breaks" aria-live="polite">
          {tests.map((t) => (
            <li key={t.mutation} className={t.caught ? "ok" : "bad"}>
              {t.caught ? <ShieldCheck size={18} weight="fill" aria-hidden="true" /> : <WarningCircle size={18} weight="fill" aria-hidden="true" />}{" "}
              <strong>{t.label}:</strong> {t.caught ? `caught: ${t.failed.map((f) => NICE[f] ?? f.replace(/_/g, " ")).join("; ")}` : "NOT caught"}
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
