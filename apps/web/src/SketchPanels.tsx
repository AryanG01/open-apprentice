import { CheckCircle, UploadSimple, WarningCircle } from "@phosphor-icons/react";
import type { AdaptLayer, PageCheck, PageInfo } from "./types";
import { LABEL, hexOr } from "./LayerEditor";

/** The story card's headline frame fits about this many characters; longer copy makes the app ask how to fit it. */
export const CARD_FITS = 44;
export const PALETTE = ["#1d1240", "#0f2440", "#14342b", "#f2efe8", "#111110", "#ffffff"] as const;

export type Picture = { url: string; img: HTMLImageElement; name: string };

export function loadPicture(src: string, name: string): Promise<Picture> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve({ url: src, img, name });
    img.onerror = () => reject(new Error("That file is not an image the browser can read."));
    img.src = src;
  });
}

export function readFileAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(String(r.result));
    r.onerror = () => reject(new Error("Could not read that file."));
    r.readAsDataURL(file);
  });
}

/** A picture drawn into a transparent PNG exactly as large as its box, fitted inside it and never stretched. */
export function renderPicture(img: HTMLImageElement, w: number, h: number): string {
  const cw = Math.max(1, Math.round(w));
  const ch = Math.max(1, Math.round(h));
  const c = document.createElement("canvas");
  c.width = cw;
  c.height = ch;
  const ctx = c.getContext("2d");
  if (!ctx) throw new Error("This browser cannot draw images.");
  ctx.imageSmoothingQuality = "high";
  const k = Math.min(cw / img.naturalWidth, ch / img.naturalHeight);
  const dw = img.naturalWidth * k;
  const dh = img.naturalHeight * k;
  ctx.drawImage(img, (cw - dw) / 2, (ch - dh) / 2, dw, dh);
  return c.toDataURL("image/png");
}

/** The sketched box shrunk to the picture's proportions around its centre, so no padding is needed. */
export function fitBoxTo(box: number[], img: HTMLImageElement): number[] {
  const [x, y, w, h] = box;
  const ar = img.naturalWidth / img.naturalHeight;
  const nw = Math.min(w, h * ar);
  const nh = nw / ar;
  return [x + (w - nw) / 2, y + (h - nh) / 2, nw, nh].map((v) => Math.round(v * 10) / 10);
}

interface CopyProps {
  page: PageInfo;
  choice: string;
  onChoice: (id: string, headline: string) => void;
  price: string;
  onPrice: (v: string) => void;
  cta: string;
  onCta: (v: string) => void;
  hasPrice: boolean;
  hasCta: boolean;
  disabled?: boolean;
}

/** What the page said, each fact with the words it was found in, and the headline options drafted from those facts. */
export function CopyPanel({ page, choice, onChoice, price, onPrice, cta, onCta, hasPrice, hasCta, disabled }: CopyProps) {
  const host = page.url.replace(/^https?:\/\//, "").replace(/\/$/, "");
  const rows: [string, string, string][] = [];
  if (page.facts.product_name) rows.push(["Product", page.facts.product_name.text, page.facts.product_name.quote]);
  for (const p of page.facts.prices.slice(0, 2)) rows.push(["Price", p.text, p.quote]);
  for (const f of page.facts.features.slice(0, 2)) rows.push(["Feature", f.text, f.quote]);
  for (const f of page.facts.legal.slice(0, 1)) rows.push(["Small print", f.text, f.quote]);
  return (
    <section className="panel" aria-labelledby="p-copy">
      <div className="panel-head">
        <h3 id="p-copy">Copy from your page</h3>
        <span className="pill ok">{page.origin === "tavily" ? "Read by Tavily" : "Offline sample page"}</span>
      </div>
      <p className="muted small">
        {host} · {page.chars.toLocaleString("en")} characters. Only facts found on the page are kept; the quote shows where.
      </p>
      {rows.length ? (
        <dl className="facts">
          {rows.map(([k, v, q], i) => (
            <div className="fact" key={`${k}-${i}`}>
              <dt>{k}</dt>
              <dd>
                <span className="fact-v">{v}</span>
                <span className="fact-q">“{q}”</span>
              </dd>
            </div>
          ))}
        </dl>
      ) : (
        <p className="callout">No facts could be read from this page, so type the words yourself.</p>
      )}
      {page.problems.length || page.copy.problems.length ? (
        <ul className="muted small">
          {[...page.problems, ...page.copy.problems].map((p) => (
            <li key={p}>{p}</li>
          ))}
        </ul>
      ) : null}
      {page.copy.options.length ? (
        <fieldset className="opts" disabled={disabled}>
          <legend className="label">Headline, {page.copy.origin === "model" ? "drafted by Nemotron-3-Super from those facts" : "the product name from your page"}</legend>
          {page.copy.options.map((o) => (
            <label key={o.id} className={choice === o.id ? "opt on" : "opt"}>
              <input type="radio" name="headline-option" value={o.id} checked={choice === o.id} onChange={() => onChoice(o.id, o.headline)} />
              <span>
                {o.headline}
                <span className="opt-tags">
                  {choice === o.id ? <span className="pill ok">names and numbers on your page</span> : null}
                  <span className={o.headline.length <= CARD_FITS ? "pill" : "pill recorded"}>{o.headline.length <= CARD_FITS ? "fits the story card" : "long: the story card will ask"}</span>
                </span>
              </span>
            </label>
          ))}
        </fieldset>
      ) : null}
      {hasPrice || hasCta ? (
        <div className="pair">
          {hasPrice ? (
            <label>
              Price line
              <input type="text" value={price} onChange={(e) => onPrice(e.target.value)} disabled={disabled} />
            </label>
          ) : null}
          {hasCta ? (
            <label>
              Button label
              <input type="text" value={cta} onChange={(e) => onCta(e.target.value)} disabled={disabled} />
            </label>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

interface PicProps {
  layers: AdaptLayer[];
  pics: Record<string, Picture>;
  onPick: (role: string, file: File | undefined) => void;
  onSample: () => void;
  disabled?: boolean;
}

/** One slot per picture box in the sketch. The box refits to the picture, which is never stretched. */
export function PicturesPanel({ layers, pics, onPick, onSample, disabled }: PicProps) {
  const roles = layers.filter((l) => l.role === "brand_mark" || l.role === "product_image").map((l) => l.role);
  return (
    <section className="panel" aria-labelledby="p-pics">
      <div className="panel-head">
        <h3 id="p-pics">Your pictures</h3>
        <button type="button" className="btn small" onClick={onSample} disabled={disabled}>
          Use the sample pictures
        </button>
      </div>
      <div className="slots">
        {roles.map((role) => {
          const pic = pics[role];
          return (
            <div className="slot" key={role}>
              <div className="slot-th">{pic ? <img src={pic.url} alt={`${LABEL[role]} you chose`} /> : <span className="muted small">None yet</span>}</div>
              <div>
                <strong>{LABEL[role]}</strong>
                <p className="muted small">{pic ? `${pic.name}: the box refits to ${pic.img.naturalWidth} × ${pic.img.naturalHeight}` : "PNG or JPEG. A transparent PNG works best."}</p>
              </div>
              <label className="btn small filebtn">
                <UploadSimple size={16} weight="bold" aria-hidden="true" />
                {pic ? "Replace" : "Choose"}
                <input type="file" accept="image/png,image/jpeg" aria-label={`${LABEL[role]} picture`} disabled={disabled} onChange={(e) => onPick(role, e.target.files?.[0])} />
              </label>
            </div>
          );
        })}
      </div>
    </section>
  );
}

export function ColourPanel({ value, onChange, disabled }: { value: string; onChange: (v: string) => void; disabled?: boolean }) {
  return (
    <section className="panel" aria-labelledby="p-colour">
      <h3 id="p-colour">Colours</h3>
      <div className="swatches" role="radiogroup" aria-label="Background colour">
        {PALETTE.map((c) => (
          <button key={c} type="button" role="radio" aria-checked={value.toLowerCase() === c} aria-label={c} className={value.toLowerCase() === c ? "swatch on" : "swatch"} style={{ background: c }} onClick={() => onChange(c)} disabled={disabled} />
        ))}
        <input type="color" aria-label="Custom background colour" value={hexOr(value, "#1d1240")} onChange={(e) => onChange(e.target.value)} disabled={disabled} />
      </div>
      <p className="muted small">Text colours are chosen for contrast. Flat colours only for now.</p>
    </section>
  );
}

/** Advisory only: the banner's price against the prices on the page the owner pointed to. Never blocks a result. */
export function PageCheckBox({ check, error }: { check: PageCheck | null; error: string }) {
  if (!check && !error) return null;
  const status = check?.status ?? "unknown";
  const tone = status === "match" ? "callout ok" : status === "mismatch" ? "callout bad" : "callout";
  return (
    <section aria-labelledby="p-check" className="pagecheck">
      <h3 id="p-check">
        Page check <span className="muted small">(advisory: it never blocks a result)</span>
      </h3>
      <div className={tone}>
        {status === "match" ? <CheckCircle size={22} weight="fill" aria-hidden="true" className="callout-icon" /> : <WarningCircle size={22} weight="fill" aria-hidden="true" className="callout-icon" />}
        <div>
          <span className={status === "match" ? "pill ok" : status === "mismatch" ? "pill bad" : "pill"}>{status === "match" ? "Match" : status === "mismatch" ? "Mismatch" : "Unknown"}</span>
          {error ? <p>{error}</p> : null}
          {check?.rows.map((r) => (
            <p key={r.field}>
              {r.detail}
              {r.page.length ? <span className="muted small"> Page prices: {r.page.join(", ")}.</span> : null}
            </p>
          ))}
          {check?.notes.map((n) => (
            <p key={n} className="muted small">
              {n}
            </p>
          ))}
        </div>
      </div>
    </section>
  );
}

interface ProvenanceProps {
  model: string;
  layers: AdaptLayer[];
  page: PageInfo | null;
  choice: string;
  pics: Record<string, Picture>;
  background: string;
}

/** Where every part of a sketch-built banner came from, so nothing looks conjured: what the sketch gave, what the page
 *  gave (with the quote), what the owner supplied. */
export function Provenance({ model, layers, page, choice, pics, background }: ProvenanceProps) {
  const text = (role: string) => layers.find((l) => l.role === role)?.text ?? "";
  const rows: [string, string, string][] = [["Layout", `Your sketch, read by ${model.replace(/^nvidia\//, "") || "you (manual boxes)"}`, `${layers.length} boxes; you can drag any of them`]];
  const option = page?.copy.options.find((o) => o.id === choice);
  const nameQuote = page?.facts.product_name?.quote;
  if (text("headline")) {
    rows.push(["Headline", option && option.headline === text("headline") ? "Drafted by Nemotron-3-Super from your page's facts" : "Typed by you", option && nameQuote ? `Every number and name is on your page, for example “${nameQuote}”` : ""]);
  }
  const price = page?.facts.prices.find((p) => text("price").includes(p.text));
  if (text("price")) rows.push(["Price", price ? "Your page, word for word" : "Typed by you", price ? `“${price.quote}”` : ""]);
  if (text("cta")) rows.push(["Button label", page && text("cta") === page.copy.cta ? "A fixed table of button words for the page's language" : "Typed by you", ""]);
  const legal = page?.facts.legal.find((f) => text("legal").includes(f.text.replace(/\.$/, "")));
  if (text("legal")) rows.push(["Small print", legal ? "Your page, word for word" : "Typed by you", legal ? `“${legal.quote}”` : ""]);
  for (const role of ["brand_mark", "product_image"]) {
    if (layers.some((l) => l.role === role)) rows.push([LABEL[role], `Your file${pics[role] ? `: ${pics[role].name}` : ""}`, "Never generated or altered, only fitted inside its box"]);
  }
  rows.push(["Background", "The colour you picked", background]);
  return (
    <details className="provenance">
      <summary>Where every part came from</summary>
      <table className="data">
        <tbody>
          {rows.map(([k, v, note]) => (
            <tr key={k}>
              <td>{k}</td>
              <td>{v}</td>
              <td className="muted small">{note}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  );
}
