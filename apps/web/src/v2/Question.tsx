import { useState } from "react";
import { ApiError, post, url } from "./api";
import { SAFETY_LINE } from "./DocumentView";
import type { Outstanding } from "./types";

type Props = { sid: string; q: Outstanding; onAnswered: () => void; names?: Record<string, string> };

function ItemImage({ sid, q, item, alt }: { sid: string; q: Outstanding; item: string; alt: string }) {
  return <img className="item" src={url(`/sessions/${sid}/requests/${q.request_id}/items/${encodeURIComponent(item)}.png`)} alt={alt} />;
}

/** Renders the open question by type and submits one answer per click (spec 8 Clarify, Preview, Review revision). */
export function Question({ sid, q, onAnswered, names = {} }: Props) {
  const docName = (sceneId: string): string => {
    const id = sceneId.split(":")[0];
    return names[id] ?? id.slice(0, 8);
  };
  const [choice, setChoice] = useState<string>("");
  const [verdicts, setVerdicts] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const req = q.request;

  const send = async (answer: Record<string, unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await post(`/sessions/${sid}/responses`, { request_id: q.request_id, intent_revision: q.intent_revision, ...answer });
      onAnswered();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const plain = (kind: "none" | "unsure" | "cancel") => (
    <button type="button" disabled={busy} onClick={() => void send({ kind })}>
      {kind === "none" ? "None" : kind === "unsure" ? "Not sure" : "Cancel"}
    </button>
  );

  return (
    <section className="question" data-request-id={q.request_id} aria-live="polite">
      {req.type === "ChooseOutput" ? (
        <>
          <h3>Which result did you mean?</h3>
          <div className="v2-options">
            {req.alternatives.map(([id]) => (
              <label key={id} className="v2-option">
                <input type="radio" name="alt" value={id} checked={choice === id} onChange={() => setChoice(id)} /> Option {id}
                <ItemImage sid={sid} q={q} item={id} alt={`Option ${id} on document ${docName(req.scene_id)}`} />
              </label>
            ))}
          </div>
          <div className="actions">
            <button type="button" disabled={busy || !choice} onClick={() => void send({ kind: "choose", selected: choice })}>Submit answer</button>
            {plain("none")} {plain("unsure")} {plain("cancel")}
          </div>
        </>
      ) : req.type === "ConfirmPreview" ? (
        <>
          <h3>{req.purpose === "affected_examples" ? "Affected examples" : req.purpose === "revision_preview" ? "Revision preview" : "Preview"}</h3>
          <p>Check each document. Approving says this output is right; nothing is kept until every check passes.</p>
          <div className="v2-options">
            {req.items.map(([id, sceneId]) => {
              const check = q.checks[id] ?? { ok: true, reasons: [] };
              const v = verdicts[id] ?? "";
              return (
                <fieldset key={id} className={`v2-option${check.ok ? "" : " blocked"}`} data-item={id}>
                  <legend>Document {docName(sceneId)}</legend>
                  <ItemImage sid={sid} q={q} item={id} alt={`Proposed output on document ${docName(sceneId)}`} />
                  {check.ok ? null : (
                    <p className="err" role="note">
                      <span aria-hidden="true">⛔ </span>Blocked: {check.reasons.join("; ")}
                    </p>
                  )}
                  {(["approve", "reject", "unsure"] as const).map((k) => (
                    <label key={k}>
                      <input type="radio" name={`v-${id}`} value={k} checked={v === k} disabled={k === "approve" && !check.ok}
                        onChange={() => setVerdicts((x) => ({ ...x, [id]: k }))} />{" "}
                      {k === "approve" ? "Approve" : k === "reject" ? "Reject" : "Not sure"}
                    </label>
                  ))}
                </fieldset>
              );
            })}
          </div>
          <div className="actions">
            <button type="button" disabled={busy || req.items.some(([id]) => !verdicts[id])}
              onClick={() => void send({ kind: "items", per_item: req.items.map(([id]) => [id, verdicts[id]]) })}>
              Submit verdicts
            </button>
          </div>
        </>
      ) : req.type === "ConfirmCorrectionScope" ? (
        <>
          <h3>How should your correction be kept?</h3>
          <div className="v2-options">
            {req.interpretations.map((it) => (
              <label key={it.interp_id} className="v2-option">
                <input type="radio" name="interp" value={it.interp_id} checked={choice === it.interp_id} onChange={() => setChoice(it.interp_id)} />{" "}
                {it.kind === "revise" ? (
                  <>
                    <strong>Change the skill:</strong> {it.summary} <span className="scope">(applies to labels where <code>{it.selector}</code>)</span>
                  </>
                ) : it.kind === "override" ? (
                  <strong>Keep this edit on this document only</strong>
                ) : (
                  <strong>That edit was a mistake</strong>
                )}
                {it.consequences.map(([sceneId], k) => (
                  <ItemImage key={k} sid={sid} q={q} item={`${it.interp_id}:${k}`} alt={`Consequence on document ${docName(sceneId)}`} />
                ))}
              </label>
            ))}
          </div>
          <div className="actions">
            <button type="button" disabled={busy || !choice} onClick={() => void send({ kind: "select", selected: choice })}>Submit answer</button>
            {plain("none")} {plain("unsure")} {plain("cancel")}
          </div>
        </>
      ) : null}
      <small className="safety">{SAFETY_LINE}</small>
      {error ? <p className="err" role="alert">{error}</p> : null}
    </section>
  );
}
