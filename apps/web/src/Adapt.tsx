import { useCallback, useEffect, useRef, useState } from "react";
import type { DragEvent } from "react";
import { PreviewCard, call, outcomeLabel } from "./CampaignLane";
import { BANNER_H, BANNER_W, LABEL, LayerEditor, ORDER, hexOr, isImageRole } from "./LayerEditor";
import { backgroundOf as backgroundInfo, snapBox } from "./snap";
import type { Rgb } from "./snap";
import type { AdaptBanner, AdaptLayer, AdaptUpload, CampaignEngine, CampaignFixture, CampaignRun, CampaignWorkspace } from "./types";

const SAMPLES = ["short_a", "short_b"];
const LANGUAGES = ["en", "de", "fr", "es", "it", "nl", "pt", "pl", "sv", "cs", "tr", "ro"];
const MAX_PNG_CHARS = 1_900_000; // above this a 1280 x 720 banner is sent as a JPEG instead (the server accepts both)

// ---------------------------------------------------------------- pixels: measured here, in the browser, never guessed
function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error("That file is not an image the browser can read."));
    img.src = src;
  });
}

function readAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result));
    r.onerror = () => reject(new Error("Could not read that file."));
    r.readAsDataURL(file);
  });
}

/** The banner at exactly 1280 x 720. A banner that is not 16:9 (within 5%) is refused rather than stretched. */
async function normalize(src: string): Promise<string> {
  const img = await loadImage(src);
  const ratio = img.naturalWidth / img.naturalHeight;
  if (Math.abs(ratio / (16 / 9) - 1) > 0.05) {
    throw new Error(`Use a 16:9 banner (for example 1600 × 900). This image is ${img.naturalWidth} × ${img.naturalHeight}.`);
  }
  const c = document.createElement("canvas");
  c.width = BANNER_W;
  c.height = BANNER_H;
  const ctx = c.getContext("2d");
  if (!ctx) throw new Error("This browser cannot draw images.");
  ctx.imageSmoothingQuality = "high";
  ctx.drawImage(img, 0, 0, BANNER_W, BANNER_H);
  const png = c.toDataURL("image/png");
  return png.length <= MAX_PNG_CHARS ? png : c.toDataURL("image/jpeg", 0.9);
}

const median = (v: number[]): number => {
  const s = [...v].sort((a, b) => a - b);
  return s[Math.floor(s.length / 2)] ?? 0;
};
const hex = (r: number, g: number, b: number): string => "#" + [r, g, b].map((n) => Math.round(n).toString(16).padStart(2, "0")).join("");

function pixelsOf(img: HTMLImageElement): ImageData {
  const c = document.createElement("canvas");
  c.width = BANNER_W;
  c.height = BANNER_H;
  const ctx = c.getContext("2d", { willReadFrequently: true });
  if (!ctx) throw new Error("This browser cannot read pixels.");
  ctx.drawImage(img, 0, 0, BANNER_W, BANNER_H);
  return ctx.getImageData(0, 0, BANNER_W, BANNER_H);
}

/** Per-channel median colour of the pixels at the given points. */
function colourAt(d: ImageData, pts: [number, number][]): string {
  const ch = [[], [], []] as number[][];
  for (const [x, y] of pts) {
    const i = (Math.min(BANNER_H - 1, Math.max(0, Math.round(y))) * BANNER_W + Math.min(BANNER_W - 1, Math.max(0, Math.round(x)))) * 4;
    for (let k = 0; k < 3; k++) ch[k].push(d.data[i + k]);
  }
  return hex(median(ch[0]), median(ch[1]), median(ch[2]));
}

/** The button plate: the median colour of a thin ring just inside its box. */
function plateOf(d: ImageData, [x, y, w, h]: number[]): string {
  const pts: [number, number][] = [];
  for (let i = 0; i <= 20; i++) pts.push([x + 3 + ((w - 6) * i) / 20, y + 3], [x + 3 + ((w - 6) * i) / 20, y + h - 4]);
  for (let i = 0; i <= 8; i++) pts.push([x + 3, y + 3 + ((h - 6) * i) / 8], [x + w - 4, y + 3 + ((h - 6) * i) / 8]);
  return colourAt(d, pts);
}

function lum(h: string): number {
  const f = (c: number): number => {
    const v = c / 255;
    return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * f(parseInt(h.slice(1, 3), 16)) + 0.7152 * f(parseInt(h.slice(3, 5), 16)) + 0.0722 * f(parseInt(h.slice(5, 7), 16));
}
const readableOn = (bg: string): string => {
  const ratio = (a: string, b: string): number => (Math.max(lum(a), lum(b)) + 0.05) / (Math.min(lum(a), lum(b)) + 0.05);
  return ratio("#ffffff", bg) >= ratio("#111111", bg) ? "#ffffff" : "#111111";
};

function cropPng(img: HTMLImageElement, [x, y, w, h]: number[]): string {
  const c = document.createElement("canvas");
  c.width = Math.max(1, Math.round(w));
  c.height = Math.max(1, Math.round(h));
  c.getContext("2d")?.drawImage(img, x, y, w, h, 0, 0, c.width, c.height);
  return c.toDataURL("image/png");
}

// ---------------------------------------------------------------- the page
type Banners = { original: string; rebuilt: string };

export function Adapt() {
  const [wid, setWid] = useState<string | null>(null);
  const [image, setImage] = useState<string | null>(null);
  const [upload, setUpload] = useState<AdaptUpload | null>(null);
  const [layers, setLayers] = useState<AdaptLayer[]>([]);
  const [background, setBackground] = useState("#1d1240");
  const [language, setLanguage] = useState("en");
  const [link, setLink] = useState("");
  const [banner, setBanner] = useState<(AdaptBanner & Banners) | null>(null);
  const [run, setRun] = useState<CampaignRun | null>(null);
  const [engine, setEngine] = useState<CampaignEngine>("konva");
  const [samples, setSamples] = useState<CampaignFixture[]>([]);
  const [status, setStatus] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [over, setOver] = useState(false);
  const [snapNote, setSnapNote] = useState("");
  const [flat, setFlat] = useState(false);
  const imgEl = useRef<HTMLImageElement | null>(null);
  const pix = useRef<{ d: ImageData; rgb: Rgb } | null>(null);
  const started = useRef(false);
  const heading = useRef<HTMLHeadingElement>(null);

  const step = run ? 3 : upload ? 2 : 1;
  useEffect(() => {
    heading.current?.focus();
  }, [step, run?.status]);

  const newWorkspace = useCallback(async (): Promise<string> => {
    const w = await call<CampaignWorkspace>("/api/campaign/workspaces", { reading: "fixed" });
    setWid(w.workspace_id);
    return w.workspace_id;
  }, []);

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    newWorkspace().catch((e: Error) => setError(`The banner tool needs the backend (${e.message}).`));
    call<{ fixtures: CampaignFixture[] }>("/api/campaign/fixtures")
      .then((r) => setSamples(r.fixtures.filter((f) => SAMPLES.includes(f.id))))
      .catch(() => undefined);
  }, [newWorkspace]);

  const go = async (text: string, fn: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    setStatus(text);
    try {
      await fn();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
      setStatus("");
    }
  };

  const reset = () => {
    setImage(null);
    setUpload(null);
    setLayers([]);
    setBanner(null);
    setRun(null);
    setLink("");
    setError(null);
  };

  const readBanner = (src: string) =>
    go("Nemotron is reading your banner. This takes about 10 to 30 seconds.", async () => {
      const url = await normalize(src);
      const img = await loadImage(url);
      imgEl.current = img;
      let id = wid ?? (await newWorkspace());
      const post = () => call<AdaptUpload>(`/api/campaign/workspaces/${id}/uploads`, { image: url });
      let up: AdaptUpload;
      try {
        up = await post();
      } catch (e) {
        if (!/holds \d+ banners at most/.test((e as Error).message)) throw e;
        id = await newWorkspace(); // a workspace holds a few banners; carry on in a fresh one
        up = await post();
      }
      const d = pixelsOf(img);
      const info = backgroundInfo(d);
      const bg = hex(...info.rgb);
      pix.current = { d, rgb: info.rgb };
      // Nemotron's boxes are often too narrow or too loose; pixels are measured exactly, so on a flat background they are
      // grown to the content and tightened to it (and the owner is told).
      const snapped = up.origin === "model" && info.flat ? up.layers.map((l) => ({ ...l, box: snapBox(d, l.box, info.rgb).map(Math.round) })) : up.layers;
      setFlat(info.flat);
      setSnapNote(up.origin === "model" && info.flat ? "The boxes were snapped to what is in the image." : info.flat ? "" : "This banner's background is not a flat colour, so boxes are not snapped: place them yourself.");
      const filled = snapped.map((l) => {
        const plate = l.role === "cta" ? hexOr(l.fill, plateOf(d, l.box)) : "";
        return { ...l, fill: plate, color: hexOr(l.color, readableOn(l.role === "cta" ? plate : bg)) };
      });
      setImage(url);
      setUpload(up);
      setLayers(filled);
      setBackground(bg);
      setLanguage(up.language || "en");
    });

  const snapAll = () => {
    const c = pix.current;
    if (!c) return;
    setLayers((ls) => ls.map((l) => ({ ...l, box: snapBox(c.d, l.box, c.rgb, { flat }).map(Math.round) })));
    setSnapNote("The boxes were snapped to what is in the image.");
  };

  const onFile = async (file: File | undefined) => {
    if (!file) return;
    if (!/^image\/(png|jpeg)$/.test(file.type)) {
      setError("Use a PNG or JPEG image.");
      return;
    }
    try {
      await readBanner(await readAsDataUrl(file));
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const onDrop = (e: DragEvent<HTMLElement>) => {
    e.preventDefault();
    setOver(false);
    void onFile(e.dataTransfer.files[0]);
  };

  const makeCards = async (bannerId: string) => {
    if (!wid) return;
    setStatus("Adapting it to a story card and checking the result…");
    setRun(await call<CampaignRun>(`/api/campaign/workspaces/${wid}/runs`, { fixture_id: bannerId, backend: engine }));
  };

  const confirm = () =>
    go("Rebuilding your banner as editable layers…", async () => {
      const img = imgEl.current;
      if (!wid || !upload || !img || !image) return;
      const missing = ORDER.filter((r) => !layers.some((l) => l.role === r));
      if (missing.length) throw new Error(`Add the missing part${missing.length > 1 ? "s" : ""}: ${missing.map((r) => LABEL[r].toLowerCase()).join(", ")}.`);
      const crops: Record<string, string> = {};
      for (const l of layers) if (isImageRole(l.role)) crops[l.role] = cropPng(img, l.box);
      const b = await call<AdaptBanner>(`/api/campaign/workspaces/${wid}/uploads/${upload.upload_id}/confirm`, {
        layers,
        background,
        locale: language,
        link: link.trim() || null,
        crops,
      });
      setBanner({ ...b, original: image, rebuilt: b.png });
      await makeCards(b.banner_id);
    });

  const answer = (choice: string) =>
    go("Applying your choice and checking it…", async () => {
      if (!wid || !run) return;
      setRun(await call<CampaignRun>(`/api/campaign/workspaces/${wid}/runs/${run.run_id}/answer`, { choice }));
    });

  const verification = run?.result?.verification ?? null;
  const passed = verification ? verification.checks.filter((c) => c.passed).length : 0;
  const finished = run && (run.status === "ready" || run.status === "applied");

  return (
    <main className="page adapt" id="stage">
      <p className="eyebrow">Adapt a banner</p>
      <h2 tabIndex={-1} ref={heading}>
        {step === 1 ? "Bring a banner. Get story cards you can trust." : step === 2 ? "Check what Nemotron found" : finished ? "Your story card" : run?.status === "question" ? "It needs one decision from you" : "Your banner"}
      </h2>
      <p className="lede">
        Drop a 16:9 banner image. Nemotron reads its parts, you check them, and the apprentice rebuilds it as editable layers, adapts it to a 9:16 story card, asks before it
        guesses, and checks every result before you see it.
      </p>

      <ol className="who" aria-label="Who does what">
        <li>
          <strong>Nemotron-3.5-Super-VL</strong> reads your banner
        </li>
        <li>
          <strong>You</strong> check the parts
        </li>
        <li>
          <strong>Deterministic checks and an independent verifier</strong> decide
        </li>
        <li>
          <strong>Nemotron-3-Super</strong> words the question when the copy does not fit
        </li>
      </ol>

      {error ? (
        <p className="callout bad" role="alert">
          {error}
        </p>
      ) : null}
      <p className="status" role="status" aria-live="polite">
        {busy ? status : ""}
      </p>

      {step === 1 ? (
        <section aria-labelledby="a-choose" className={over ? "drop over" : "drop"} onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)} onDrop={onDrop}>
          <h3 id="a-choose">1. Choose a banner</h3>
          <label className="btn primary filebtn">
            Choose a banner image (PNG or JPEG)
            <input type="file" accept="image/png,image/jpeg" disabled={busy || !wid} onChange={(e) => void onFile(e.target.files?.[0])} />
          </label>
          <span className="muted"> or drop one here. 16:9 works best (for example 1600 × 900).</span>
          {samples.length ? (
            <div className="samples-row">
              <p className="muted small">Or try a sample banner:</p>
              <div className="samples">
                {samples.map((f) => (
                  <button key={f.id} className="samplebtn" disabled={busy || !wid} onClick={() => void readBanner(f.png)}>
                    <img src={f.png} alt="" className="thumb" />
                    <strong>{f.id === "short_a" ? "Headphones, English" : "Headphones, new copy"}</strong>
                  </button>
                ))}
              </div>
            </div>
          ) : null}
          <p className="muted small">
            Your banner is sent to NVIDIA Nemotron on Nebius Token Factory to read its layers, and kept in server memory for 30 minutes. Fonts are replaced with Liberation Sans.
          </p>
        </section>
      ) : null}

      {step === 2 && upload && image ? (
        <section aria-labelledby="a-check">
          <h3 id="a-check">2. Check the parts</h3>
          <p className={upload.origin === "model" ? "callout ok" : "callout"}>
            {upload.origin === "model" ? (
              <>
                <strong>Nemotron read this banner</strong> ({upload.model.replace(/^nvidia\//, "")}). Boxes can be tight around the words; fix anything that is off, then continue.
              </>
            ) : (
              <>
                <strong>Place the parts yourself.</strong> {upload.note || "No vision model answered."} Drag each box onto its part and type the words.
              </>
            )}
            {upload.problems.length ? (
              <ul>
                {upload.problems.map((p) => (
                  <li key={p}>{p}</li>
                ))}
              </ul>
            ) : null}
          </p>
          {snapNote ? <p className="muted small">{snapNote}</p> : null}
          <LayerEditor image={image} layers={layers} onChange={setLayers} disabled={busy} />
          <div className="lextras">
            <button type="button" className="btn" onClick={snapAll} disabled={busy || !flat} title={flat ? undefined : "Only works on a flat background"}>
              Snap boxes to the content
            </button>
            <label>
              Background colour
              <input type="color" value={hexOr(background, "#000000")} onChange={(e) => setBackground(e.target.value)} />
            </label>
            <label>
              Language (2 letters)
              <input type="text" list="a-langs" maxLength={2} pattern="[a-z]{2}" value={language} onChange={(e) => setLanguage(e.target.value.toLowerCase())} />
              <datalist id="a-langs">
                {LANGUAGES.map((l) => (
                  <option key={l} value={l} />
                ))}
              </datalist>
            </label>
            <label>
              Button link (optional, https)
              <input type="url" placeholder="https://" value={link} onChange={(e) => setLink(e.target.value)} />
            </label>
          </div>
          <details>
            <summary>More options</summary>
            <fieldset className="controls" disabled={busy}>
              <legend className="muted small">Graphics engine</legend>
              {(["konva", "fabric"] as const).map((e) => (
                <label key={e}>
                  <input type="radio" name="adapt-engine" value={e} checked={engine === e} onChange={() => setEngine(e)} /> {e === "konva" ? "Konva" : "Fabric"}
                </label>
              ))}
            </fieldset>
          </details>
          <div className="controls">
            <button className="btn primary" onClick={() => void confirm()} disabled={busy}>
              Looks right: make the story card
            </button>
            <button className="btn" onClick={reset} disabled={busy}>
              Start over
            </button>
          </div>
        </section>
      ) : null}

      {step === 3 && run && banner ? (
        <section aria-labelledby="a-result">
          <h3 id="a-result">3. Your story cards</h3>
          <div className="trio">
            <figure>
              <img src={banner.original} alt="Your banner" />
              <figcaption>Your banner</figcaption>
            </figure>
            <span aria-hidden="true" className="arrow">→</span>
            <figure>
              <img src={banner.rebuilt} alt="Your banner rebuilt as editable layers" />
              <figcaption>Rebuilt as editable layers</figcaption>
            </figure>
            <span aria-hidden="true" className="arrow">→</span>
            <figure className={finished ? "" : "pending"}>
              {run.result ? <img src={run.result.png} alt="The story card" /> : <div className="placeholder">{run.status === "question" ? "Waiting for your decision" : "No result yet"}</div>}
              <figcaption>{finished ? "Story card, 1080 × 1920" : "Story card"}</figcaption>
            </figure>
          </div>

          {run.status === "question" ? (
            <div className="question" aria-label="Question">
              <p>
                <strong>The copy does not fit, so it is asking instead of guessing.</strong>{" "}
                {run.explanation ? (
                  <>
                    {run.explanation.text}{" "}
                    <span className="muted small">
                      ({run.explanation.origin === "model" ? "wording by Nemotron-3-Super, every number checked against the measured facts" : "built-in wording"})
                    </span>
                  </>
                ) : null}
              </p>
              <div className="previews">
                {run.previews.map((p) => (
                  <PreviewCard key={p.outcome} p={p} busy={busy} onPick={(o) => void answer(o)} />
                ))}
              </div>
              <button className="btn" onClick={() => void answer("neither")} disabled={busy}>
                Neither: leave it unchanged
              </button>
            </div>
          ) : null}

          {run.status === "blocked" || run.status === "failed" || run.status === "unsupported_format" || run.status === "needs_roles" ? (
            <p className="callout bad" role="alert">
              <strong>Not applied.</strong> {run.problems.join("; ") || (verification ? `The independent verifier refused this result (failed: ${verification.failed.join(", ")}).` : "Something went wrong.")} Your banner is unchanged.
            </p>
          ) : null}
          {run.status === "unchanged" ? <p className="callout">You chose neither, so nothing was changed.</p> : null}

          {finished && verification ? (
            <>
              <p className="callout ok">
                <strong>
                  {passed} of {verification.checks.length} checks passed
                </strong>{" "}
                <span className="muted small">
                  independent verifier: exact copy, link, logo, image proportions, safe areas, minimum sizes, text fit. It has no authored expected output for your banner, so that comparison is not part of these checks.
                </span>
                {run.preference ? (
                  <>
                    {" "}
                    <span className="pill ok">saved: {outcomeLabel(run.preference.outcome)} for {run.locale}</span>
                  </>
                ) : null}
              </p>
              <details>
                <summary>See every check</summary>
                <div className="table-wrap">
                  <table className="data">
                    <tbody>
                      {verification.checks.map((c) => (
                        <tr key={c.name}>
                          <td>{c.name.replace(/_/g, " ")}</td>
                          <td>{c.passed ? <span className="pill ok">pass</span> : <span className="pill bad">fail</span>}</td>
                          <td className="muted small">{c.passed ? "" : c.detail}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </details>
              <div className="controls">
                <a className="btn primary" href={run.result?.png} download="story-card.png">
                  Download the story card (PNG)
                </a>
                <button className="btn" onClick={reset}>
                  Adapt another banner
                </button>
              </div>
            </>
          ) : (
            <div className="controls">
              <button className="btn" onClick={reset} disabled={busy}>
                Start over
              </button>
            </div>
          )}
        </section>
      ) : null}

      <details className="limits">
        <summary>What it cannot do yet</summary>
        <ul>
          <li>It works best on flat or simple backgrounds: the logo and product are cropped as rectangles and the rest is rebuilt as a solid colour.</li>
          <li>Text is rebuilt in Liberation Sans; scripts that font cannot draw (Chinese, Japanese, Korean, Arabic, Hindi) are refused.</li>
          <li>All six parts are required (logo, product image, headline, price, button, small print), and the product image must be larger than the logo.</li>
          <li>Banners must be 16:9; one story-card layout (1080 × 1920) is learned from a single example.</li>
          <li>Nemotron can misplace or merge boxes, so you confirm every layer. The checks are structural: they cannot judge whether the result is beautiful.</li>
          <li>Measured so far: roles and words are read well, boxes come back tight around the text (see the evaluation in the repository). No people have been studied.</li>
        </ul>
      </details>
    </main>
  );
}
