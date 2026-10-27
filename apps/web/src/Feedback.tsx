import { useState } from "react";
import { call } from "./CampaignLane";

/** Five small questions after a result. Nothing but these answers is sent (no image). */
export function Feedback({ ownBanner }: { ownBanner: boolean }) {
  const [post, setPost] = useState(0);
  const [fixes, setFixes] = useState("");
  const [words, setWords] = useState("");
  const [note, setNote] = useState("");
  const [quoteOk, setQuoteOk] = useState(false);
  const [state, setState] = useState<"idle" | "sending" | "sent" | "error">("idle");
  const ready = post > 0 && fixes && words;
  const send = async () => {
    setState("sending");
    try {
      await call("/api/campaign/feedback", { would_post: post, fixes, words_correct: words, note: note.trim(), own_banner: ownBanner, quote_ok: quoteOk });
      setState("sent");
    } catch {
      setState("error");
    }
  };
  if (state === "sent") return <p className="callout" role="status">Thank you. Your answers were saved (no image, no address).</p>;
  return (
    <section className="proof" aria-labelledby="fb-h">
      <h3 id="fb-h">How did it go?</h3>
      <p className="muted small">Three quick questions and an optional note. They help more than praise: tell us what is wrong.</p>
      <fieldset className="opts">
        <legend className="label">Would you post this card as it is?</legend>
        <div className="row">
          {[1, 2, 3, 4, 5].map((n) => (
            <label key={n} className={post === n ? "opt on" : "opt"}>
              <input type="radio" name="fb-post" checked={post === n} onChange={() => setPost(n)} /> {n}
            </label>
          ))}
        </div>
        <p className="muted small">1 = never, 5 = yes, today</p>
      </fieldset>
      <label>
        How many things did you have to fix?
        <select value={fixes} onChange={(e) => setFixes(e.target.value)}>
          <option value="">Choose</option>
          <option value="0">None</option>
          <option value="1-2">1 or 2</option>
          <option value="3-5">3 to 5</option>
          <option value="more">More than 5</option>
        </select>
      </label>
      <label>
        Are all your words, your price and your picture correct on the card?
        <select value={words} onChange={(e) => setWords(e.target.value)}>
          <option value="">Choose</option>
          <option value="yes">Yes</option>
          <option value="no">No, something is wrong</option>
        </select>
      </label>
      <label>
        What would you fix first? (optional)
        <textarea value={note} maxLength={400} onChange={(e) => setNote(e.target.value)} rows={2} />
      </label>
      <label className="check">
        <input type="checkbox" checked={quoteOk} onChange={(e) => setQuoteOk(e.target.checked)} /> The team may quote my note without my name.
      </label>
      <div className="row">
        <button type="button" className="btn" disabled={!ready || state === "sending"} onClick={() => void send()}>
          Send
        </button>
      </div>
      {state === "error" ? <p className="callout bad" role="alert">Could not send. Try again in a moment.</p> : null}
    </section>
  );
}
