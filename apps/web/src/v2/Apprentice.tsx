import { useCallback, useEffect, useState } from "react";
import { ImportMap } from "./ImportMap";
import { Question } from "./Question";
import { Teach } from "./Teach";
import { get } from "./api";
import { useSession } from "./useSession";
import type { DocumentInfo, Provenance } from "./types";

const DOCS_KEY = "oa.v2.docs";

const STATE_TEXT: Record<string, string> = {
  teaching: "teaching",
  waiting_for_model: "waiting for the learner",
  waiting_for_answer: "waiting for your answer",
  preview_ready: "preview ready",
  committed: "committed",
  failed: "stopped",
  cancelled: "cancelled",
  review: "review",
  activated: "activated",
  override: "kept as a one-document override",
};

export const provenanceLine = (p: Provenance): string => `Model: ${p.model} · Teacher: ${p.teacher}`;

function readHash(): { sid: string | null } {
  const m = window.location.hash.match(/^#apprentice\/s\/([0-9a-f]+)/);
  return { sid: m ? m[1] : null };
}

function loadIds(): string[] {
  try {
    return JSON.parse(localStorage.getItem(DOCS_KEY) ?? "[]") as string[];
  } catch {
    return [];
  }
}

/** The teach → clarify → correct → reuse flow on real .drawio files (spec 8). */
export function Apprentice() {
  const [docs, setDocsState] = useState<DocumentInfo[]>([]);
  const [sid, setSid] = useState<string | null>(readHash().sid);
  const { state, error, refresh } = useSession(sid);
  const [backend, setBackend] = useState<"unknown" | "yes" | "no">("unknown");

  const setDocs = useCallback((f: (d: DocumentInfo[]) => DocumentInfo[]) => {
    setDocsState((old) => {
      const next = f(old);
      try {
        localStorage.setItem(DOCS_KEY, JSON.stringify(next.map((d) => d.doc_id)));
      } catch {
        /* storage unavailable: documents are kept for this page only */
      }
      return next;
    });
  }, []);

  useEffect(() => {
    get("/config").then(() => setBackend("yes")).catch(() => setBackend("no"));
  }, []);

  // reload resumes: documents from local storage, the session from the URL
  useEffect(() => {
    const ids = loadIds();
    Promise.all(ids.map((id) => get<DocumentInfo>(`/documents/${id}`).catch(() => null))).then((all) =>
      setDocsState(all.filter((d): d is DocumentInfo => d !== null)),
    );
    const onHash = () => setSid(readHash().sid);
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const openSession = (id: string) => {
    window.location.hash = `apprentice/s/${id}`;
    setSid(id);
  };

  return (
    <main className="page apprentice" id="stage">
      {backend === "no" ? (
        <div className="banner" role="note">
          <span className="pill recorded">NOT AVAILABLE IN THIS COPY</span>
          <span>This copy has no backend. Teaching on .drawio files needs the full server; the earlier prototype&apos;s walkthrough works here.</span>
        </div>
      ) : null}
      <ImportMap docs={docs} setDocs={setDocs} />
      {!sid ? <Teach docs={docs} onSession={openSession} /> : null}
      {sid ? (
        <section className="v2-step" aria-labelledby="h-session">
          <h2 id="h-session">Session</h2>
          {error ? <p className="err" role="alert">{error}</p> : null}
          {state ? (
            <>
              <p className="prov">{provenanceLine(state.provenance)}</p>
              <p role="status" data-state={state.state}>State: {STATE_TEXT[state.state] ?? state.state}</p>
              {state.result.reason ? <p className="err">{state.result.reason}</p> : null}
              {state.outstanding ? <Question key={state.outstanding.request_id} sid={state.session_id} q={state.outstanding} onAnswered={refresh} /> : null}
              {["teaching", "waiting_for_model", "draft"].includes(state.state) ? <p role="status">Working…</p> : null}
              <details>
                <summary>Evidence</summary>
                <pre>{JSON.stringify({ state: state.state, budgets: state.budgets, spend: state.spend, result: state.result }, null, 1)}</pre>
              </details>
            </>
          ) : (
            <p role="status">Loading…</p>
          )}
          <button type="button" onClick={() => { window.location.hash = "apprentice"; setSid(null); }}>Start over with these documents</button>
        </section>
      ) : null}
    </main>
  );
}
