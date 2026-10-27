import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { DragEvent } from "react";
import { lazy, Suspense } from "react";
import { ArrowRight, CheckCircle, DownloadSimple, UploadSimple, WarningCircle } from "@phosphor-icons/react";
import { PreviewCard, call, outcomeLabel } from "./CampaignLane";
import { BANNER_H, BANNER_W, LABEL, LayerEditor, REQUIRED, hexOr, isImageRole } from "./LayerEditor";
import { noFitReasons } from "./reasons";
import { ProofPanel } from "./Proof";
import { backgroundOf as backgroundInfo, clippedSides, foreignRuns, imageTextOverlaps, inkComponents, pictureComponents, reassignText, snapBox, unionBox } from "./snap";
import type { Components, Rgb } from "./snap";
import { CARD_FITS, ColourPanel, CopyPanel, PALETTE, PageCheckBox, PicturesPanel, Provenance, fitBoxTo, loadPicture, readFileAsDataUrl, renderPicture } from "./SketchPanels";
import type { Picture } from "./SketchPanels";
import type { AdaptBanner, AdaptLayer, AdaptUpload, CampaignEngine, CampaignFixture, CampaignRun, CampaignWorkspace, PageCheck, PageInfo } from "./types";

const ReadingLoader = lazy(() => import("./ReadingLoader").then((m) => ({ default: m.ReadingLoader })));
const SAMPLES = ["short_a", "short_b"];
/** A server note as a sentence: first letter capital, one full stop. */
const sentence = (t: string): string => {
  const x = t.trim().replace(/[.\s]+$/, "");
  return x ? `${x[0].toUpperCase()}${x.slice(1)}.` : "";
};
/** A sketch's text boxes are drawn small and loose. Give each text block the free space below it (down to the next part that
 *  overlaps it in x, or the bottom margin) and generous type caps, so the rebuilt banner reads as designed, not as a wireframe
 *  with words in it. The server still fits the size to the box; the owner can drag any box. */
const TEXT_CAP: Record<string, number> = { headline: 72, price: 48, cta: 36, legal: 20 };
const TEXT_MAX_H: Record<string, number> = { headline: 230, price: 80, legal: 100 };
function growText(ls: AdaptLayer[]): AdaptLayer[] {
  const GAP = 20;
  return ls.map((l) => {
    if (isImageRole(l.role)) return l;
    const cap = TEXT_CAP[l.role];
    const [x, y, w, h] = l.box;
    if (l.role === "cta") return { ...l, font_px: cap };
    const below = ls.filter((o) => o !== l && o.box[1] > y + 4 && o.box[0] < x + w && o.box[0] + o.box[2] > x).map((o) => o.box[1]);
    const free = (below.length ? Math.min(...below) : BANNER_H - 48) - GAP - y;
    const nh = Math.round(Math.min(Math.max(h, free), TEXT_MAX_H[l.role] ?? h));
    return { ...l, box: [x, y, w, nh], font_px: cap };
  });
}
const PUBLIC_DEMO = "https://open-apprentice-md76de375q-uc.a.run.app";
/** The sample product page Tavily reads. On an https deployment it is this server's own copy (so a candidate revision tests itself);
 *  locally the public demo's address stands in (the offline page reader answers for it without any network). */
const samplePageUrl = (): string => `${window.location.protocol === "https:" ? window.location.origin : PUBLIC_DEMO}/samples/halden-h7.html`;
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

/** A sketch (often a photo of paper) letterboxed onto a white 1280 x 720 canvas, so the boxes keep their relative places. */
async function normalizeSketch(src: string): Promise<string> {
  const img = await loadImage(src);
  const c = document.createElement("canvas");
  c.width = BANNER_W;
  c.height = BANNER_H;
  const ctx = c.getContext("2d");
  if (!ctx) throw new Error("This browser cannot draw images.");
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, BANNER_W, BANNER_H);
  const k = Math.min(BANNER_W / img.naturalWidth, BANNER_H / img.naturalHeight);
  const w = img.naturalWidth * k;
  const h = img.naturalHeight * k;
  ctx.imageSmoothingQuality = "high";
  ctx.drawImage(img, (BANNER_W - w) / 2, (BANNER_H - h) / 2, w, h);
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

/** The banner's pixels, with its ink labelled once (only a flat background is cleaned). */
interface Pix {
  d: ImageData;
  rgb: Rgb;
  comps?: Components;
}
const compsOf = (pix: Pix): Components => (pix.comps ??= inkComponents(pix.d, pix.rgb));

/** What a picture layer cuts out of the banner: its box, with every other object's ink painted over in the background colour, so a
 *  neighbour's fragment (the logo's tail above a lamp) is never in the picture. A picture whose own ink cannot be identified is cropped as is. */
function cleanCrop(img: HTMLImageElement, pix: Pix | null, flat: boolean, l: AdaptLayer, layers: AdaptLayer[]): string {
  const c = document.createElement("canvas");
  c.width = Math.max(1, Math.round(l.box[2]));
  c.height = Math.max(1, Math.round(l.box[3]));
  const ctx = c.getContext("2d");
  ctx?.drawImage(img, l.box[0], l.box[1], l.box[2], l.box[3], 0, 0, c.width, c.height);
  if (ctx && pix && flat) {
    const comps = compsOf(pix);
    const ids = pictureComponents(comps, l.box, layers.filter((o) => o !== l).map((o) => o.box));
    if (ids.length) {
      ctx.fillStyle = `rgb(${pix.rgb[0]},${pix.rgb[1]},${pix.rgb[2]})`;
      for (const [x, y, w, h] of foreignRuns(pix.d, comps, [Math.round(l.box[0]), Math.round(l.box[1]), c.width, c.height], ids)) ctx.fillRect(x, y, w, h);
    }
  }
  return c.toDataURL("image/png");
}

/** Text boxes may grow to the words; image boxes only a little (the model is mostly right about them). */
function snapLayer(d: ImageData, l: AdaptLayer, rgb: Rgb, flat: boolean): AdaptLayer {
  const box = snapBox(d, l.box, rgb, { flat, maxGrow: isImageRole(l.role) ? 14 : undefined }).map(Math.round);
  return { ...l, box };
}

/** What each image layer will cut out of the banner, so a crop that holds words is obvious before confirming. */
function CropPreview({ img, layers, pix, flat }: { img: HTMLImageElement | null; layers: AdaptLayer[]; pix: Pix | null; flat: boolean }) {
  const crops = useMemo(
    () => (img ? layers.filter((l) => isImageRole(l.role) && l.box.length === 4 && l.box[2] > 0 && l.box[3] > 0).map((l) => ({ role: l.role, url: cleanCrop(img, pix, flat, l, layers) })) : []),
    [img, layers, pix, flat],
  );
  if (!crops.length) return null;
  return (
    <div className="crops" aria-label="What will be cut out as pictures">
      <p className="muted small">These two parts are cut out as pictures. Everything else is rebuilt as editable text and shapes, so a picture should not contain any words.</p>
      <div className="cropthumbs">
        {crops.map((c) => (
          <figure key={c.role}>
            <img src={c.url} alt={`${LABEL[c.role]} crop`} />
            <figcaption>{LABEL[c.role]}</figcaption>
          </figure>
        ))}
      </div>
    </div>
  );
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
  const [busyBackground, setBusyBackground] = useState<string | null>(null); // the banner whose background is not a flat colour, awaiting the owner's choice
  const [busy, setBusy] = useState(false);
  const [reading, setReading] = useState(false); // Nemotron is reading an image: show the turntable
  const [over, setOver] = useState(false);
  const [snapNote, setSnapNote] = useState("");
  const [flat, setFlat] = useState(false);
  const [door, setDoor] = useState<"choose" | "sketch">("choose");
  const [kind, setKind] = useState<"banner" | "sketch">("banner");
  const [sketchSrc, setSketchSrc] = useState<string | null>(null);
  const [pageUrl, setPageUrl] = useState("");
  const [page, setPage] = useState<PageInfo | null>(null);
  const [pageNote, setPageNote] = useState("");
  const [choice, setChoice] = useState("");
  const [priceLine, setPriceLine] = useState("");
  const [ctaLabel, setCtaLabel] = useState("");
  const [pics, setPics] = useState<Record<string, Picture>>({});
  const [pageCheck, setPageCheck] = useState<PageCheck | null>(null);
  const [checkNote, setCheckNote] = useState("");
  const imgEl = useRef<HTMLImageElement | null>(null);
  const pix = useRef<Pix | null>(null);
  const started = useRef(false);
  const heading = useRef<HTMLHeadingElement>(null);

  const step = run ? 3 : upload ? 2 : 1;
  const overlaps = useMemo(() => {
    const out = imageTextOverlaps(layers).filter((m) => !(kind === "banner" && flat && /overlaps the logo/.test(m))); // a neighbour's ink is painted out of the crop on a flat background
    const px = pix.current;
    if (kind === "banner" && flat && px) {
      const comps = compsOf(px);
      for (const l of layers.filter((x) => isImageRole(x.role) && x.box.length === 4)) {
        const ids = pictureComponents(comps, l.box, layers.filter((o) => o !== l).map((o) => o.box));
        const sides = ids.length ? clippedSides(px.d, comps, l.box, ids) : [];
        if (sides.length) out.push(`${LABEL[l.role]} box cuts the picture off at the ${sides.join(" and ")}: drag that edge outwards or press “Snap boxes to the content”`);
      }
    }
    return out;
  }, [layers, kind, flat]);
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
      const m = (e as Error).message;
      if (/unknown or expired/.test(m)) {
        setWid(null); // the server dropped this workspace (30 minutes, or a restart): the next action starts a fresh one
        setError("This workspace has expired, so the choices saved in it are gone. Start over to begin a new one.");
      } else if (/saved preference changed/.test(m)) {
        setError("Your saved choice for this language changed after this question was shown, so nothing was saved. Adapt the banner again to see the current question.");
      } else setError(m);
    } finally {
      setBusy(false);
      setReading(false);
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
    setDoor("choose");
    setKind("banner");
    setSketchSrc(null);
    setPageUrl("");
    setPage(null);
    setPageNote("");
    setChoice("");
    setPriceLine("");
    setCtaLabel("");
    setPics({});
    setPageCheck(null);
    setCheckNote("");
  };

  const patchRole = (role: string, text: string) => setLayers((ls) => ls.map((l) => (l.role === role ? { ...l, text } : l)));
  const onChoice = (id: string, headline: string) => {
    setChoice(id);
    patchRole("headline", headline);
  };
  const onPrice = (v: string) => {
    setPriceLine(v);
    patchRole("price", v);
  };
  const onCta = (v: string) => {
    setCtaLabel(v);
    patchRole("cta", v);
  };
  const setPicture = async (role: string, url: string, name: string) => {
    const pic = await loadPicture(url, name);
    setPics((p) => ({ ...p, [role]: pic }));
    setLayers((ls) => ls.map((l) => (l.role === role ? { ...l, box: fitBoxTo(l.box, pic.img) } : l)));
  };
  const pickPicture = async (role: string, file: File | undefined) => {
    if (!file) return;
    try {
      await setPicture(role, await readFileAsDataUrl(file), file.name);
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const samplePictures = () =>
    go("Loading the sample pictures…", async () => {
      for (const [role, path, name] of [
        ["brand_mark", "/samples/pictures/halden-wordmark.png", "halden-wordmark.png"],
        ["product_image", "/samples/pictures/h7-headphones.png", "h7-headphones.png"],
      ] as const) {
        const blob = await (await fetch(path)).blob();
        await setPicture(role, await readFileAsDataUrl(new File([blob], name, { type: blob.type || "image/png" })), name);
      }
    });
  const onSketch = async (file: File | undefined) => {
    if (!file) return;
    if (!/^image\/(png|jpeg)$/.test(file.type)) {
      setError("Use a PNG or JPEG image.");
      return;
    }
    try {
      setSketchSrc(await readFileAsDataUrl(file));
      setError(null);
    } catch (e) {
      setError((e as Error).message);
    }
  };
  const sampleSketch = () =>
    go("Loading the sample sketch…", async () => {
      const blob = await (await fetch("/samples/sketches/sketch-4.png")).blob();
      setSketchSrc(await readFileAsDataUrl(new File([blob], "sketch-4.png", { type: blob.type || "image/png" })));
    });

  const readBanner = (src: string, accepted = false) =>
    go("Nemotron is reading your banner. This takes about 10 to 30 seconds.", async () => {
      setReading(true);
      setBusyBackground(null);
      const url = await normalize(src);
      const img = await loadImage(url);
      // a photo or busy background cannot be kept: say so BEFORE spending a model call, and let the owner choose a lossy version
      if (!accepted && !backgroundInfo(pixelsOf(img)).flat) {
        setBusyBackground(src);
        setReading(false);
        return;
      }
      imgEl.current = img;
      let id = wid ?? (await newWorkspace());
      const post = () => call<AdaptUpload>(`/api/campaign/workspaces/${id}/uploads`, { image: url });
      let up: AdaptUpload;
      try {
        up = await post();
      } catch (e) {
        if (!/holds \d+ banners at most/.test((e as Error).message)) throw e;
        id = await newWorkspace(); // a workspace holds a few banners; carry on in a fresh one (its saved choices stay behind)
        up = await post();
      }
      const d = pixelsOf(img);
      const info = backgroundInfo(d);
      const bg = hex(...info.rgb);
      pix.current = { d, rgb: info.rgb };
      // Nemotron's boxes are often too narrow or too loose; pixels are measured exactly, so on a flat background they are
      // grown to the content and tightened to it (and the owner is told).
      const notes: string[] = [];
      let snapped = up.layers;
      if (up.origin === "model" && info.flat) {
        // 1) text boxes the model put on the wrong lines (a long headline pushes the rest down) go back onto their own blocks
        const keepOut = up.layers.filter((l) => isImageRole(l.role)).map((l) => l.box);
        const re = reassignText(d, info.rgb, up.layers, keepOut);
        let work = up.layers;
        if (re) {
          const moved = re.filter((r) => { const was = up.layers.find((l) => l.role === r.role)?.box ?? r.box; return Math.abs(was[1] - r.box[1]) > 12 || Math.abs(was[0] - r.box[0]) > 12; });
          if (moved.length) notes.push(`${moved.map((m) => LABEL[m.role].toLowerCase()).join(", ")} moved onto ${moved.length > 1 ? "their own lines" : "its own line"}`);
          work = up.layers.map((l) => (re.find((r) => r.role === l.role) ? { ...l, box: (re.find((r) => r.role === l.role) as { box: number[] }).box } : l));
        }
        // 2) every box snapped to the pixels; 3) the product box fitted to the whole picture (components, not a guess)
        // text boxes that were put on measured blocks are final (snapping would grow them into their neighbours); the rest are snapped
        snapped = work.map((l) => (re && re.some((r) => r.role === l.role) && !isImageRole(l.role) ? l : snapLayer(d, l, info.rgb, true)));
        const pix0: Pix = { d, rgb: info.rgb };
        const comps = compsOf(pix0);
        const prod = snapped.find((l) => l.role === "product_image");
        if (prod) {
          const ids = pictureComponents(comps, prod.box, snapped.filter((l) => l !== prod).map((l) => l.box));
          const ub = unionBox(comps, ids, 2);
          if (ub && (Math.abs(ub[2] - prod.box[2]) > 6 || Math.abs(ub[3] - prod.box[3]) > 6 || Math.abs(ub[1] - prod.box[1]) > 6)) {
            snapped = snapped.map((l) => (l === prod ? { ...l, box: ub.map(Math.round) } : l));
            notes.push("the product box was fitted to the whole picture");
          }
        }
        pix.current = pix0;
      }
      setFlat(info.flat);
      setSnapNote(up.origin === "model" && info.flat ? `The boxes were snapped to what is in the image${notes.length ? `; ${notes.join("; ")}` : ""}.` : info.flat ? "" : "This banner's background is not a flat colour, so boxes are not snapped: place them yourself.");
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

  const readSketch = () =>
    go("Nemotron is reading your sketch. This takes about 10 to 30 seconds.", async () => {
      if (!sketchSrc) throw new Error("Choose a sketch first.");
      setReading(true);
      const url = await normalizeSketch(sketchSrc);
      imgEl.current = await loadImage(url);
      let id = wid ?? (await newWorkspace());
      const attempt = async (ws: string): Promise<[AdaptUpload, PageInfo | null, string]> => {
        const address = pageUrl.trim();
        const [up, pg] = await Promise.all([
          call<AdaptUpload>(`/api/campaign/workspaces/${ws}/sketches`, { image: url }),
          address
            ? call<PageInfo>(`/api/campaign/workspaces/${ws}/pages`, { url: address }).then(
                (p): [PageInfo | null, string] => [p, ""],
                (e: Error): [PageInfo | null, string] => [null, e.message],
              )
            : Promise.resolve<[PageInfo | null, string]>([null, ""]),
        ]);
        return [up, pg[0], pg[1]];
      };
      let got: [AdaptUpload, PageInfo | null, string];
      try {
        got = await attempt(id);
      } catch (e) {
        if (!/holds \d+ banners at most/.test((e as Error).message)) throw e;
        id = await newWorkspace(); // a workspace holds a few banners; carry on in a fresh one (its saved choices stay behind)
        got = await attempt(id);
      }
      const [up, pg, pgNote] = got;
      const copy = pg?.copy;
      if (copy?.options.length) copy.options = [...copy.options.filter((o) => o.headline.length <= CARD_FITS), ...copy.options.filter((o) => o.headline.length > CARD_FITS)]; // options that fit the card first
      const textFor = (role: string, hint: string): string => {
        const fromPage = role === "headline" ? copy?.options[0]?.headline : role === "price" ? copy?.price : role === "cta" ? copy?.cta : role === "legal" ? copy?.legal : "";
        return fromPage || hint;
      };
      setKind("sketch");
      setImage(url);
      setUpload(up);
      setLayers(growText(up.layers.map((l) => ({ ...l, color: "", fill: "", text: isImageRole(l.role) ? "" : textFor(l.role, l.text) }))));
      setBackground(PALETTE[0]);
      setLanguage(pg?.language || up.language || "en");
      setPage(pg);
      setPageNote(pgNote);
      setChoice(copy?.options[0]?.id ?? "");
      setPriceLine(copy?.price ?? "");
      setCtaLabel(copy?.cta ?? "");
      setFlat(false);
      setSnapNote("");
      setPics({});
    });

  const snapAll = () => {
    const c = pix.current;
    if (!c) return;
    setLayers((ls) => ls.map((l) => snapLayer(c.d, l, c.rgb, flat)));
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
      const missing = REQUIRED.filter((r) => !layers.some((l) => l.role === r));
      if (missing.length) throw new Error(`Add the missing part${missing.length > 1 ? "s" : ""}: ${missing.map((r) => LABEL[r].toLowerCase()).join(", ")}.`);
      const crops: Record<string, string> = {};
      for (const l of layers) {
        if (!isImageRole(l.role)) continue;
        if (kind === "sketch") {
          const pic = pics[l.role];
          if (!pic) throw new Error(`Add your ${LABEL[l.role].toLowerCase()} picture first.`);
          crops[l.role] = renderPicture(pic.img, l.box[2], l.box[3]);
        } else {
          crops[l.role] = cleanCrop(img, pix.current, flat, l, layers);
        }
      }
      if (kind === "banner" && pageUrl.trim() && !page) {
        try {
          setPage(await call<PageInfo>(`/api/campaign/workspaces/${wid}/pages`, { url: pageUrl.trim(), copy: false }));
        } catch (e) {
          setCheckNote((e as Error).message);
        }
      }
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
      setRun(await call<CampaignRun>(`/api/campaign/workspaces/${wid}/runs/${run.run_id}/answer`, { choice, expected_version: run.preference_seen ?? null }));
    });

  const verification = run?.result?.verification ?? null;
  const passed = verification ? verification.checks.filter((c) => c.passed).length : 0;
  const finished = run && (run.status === "ready" || run.status === "applied");
  useEffect(() => {
    if (!finished || !page || !banner || !wid || pageCheck) return;
    let live = true;
    call<PageCheck>(`/api/campaign/workspaces/${wid}/page-check`, { banner_id: banner.banner_id, page_id: page.page_id }).then(
      (c) => live && setPageCheck(c),
      (e: Error) => live && setCheckNote(e.message),
    );
    return () => {
      live = false;
    };
  }, [finished, page, banner, wid, pageCheck]);

  const title = step === 1 ? "Bring a banner. Get story cards, checked." : step === 2 ? "Check what Nemotron found" : finished ? "Your story card" : run?.status === "question" ? "It needs one decision from you" : "Your banner";
  const notices = (
    <>
      {error ? (
        <p className="callout bad" role="alert">
          {error}
        </p>
      ) : null}
      {busyBackground ? (
        <div className="callout" role="alert">
          <WarningCircle size={22} weight="fill" aria-hidden="true" className="callout-icon" />
          <div>
            <strong>This banner has a photo or busy background, which the app cannot keep.</strong>
            <p>
              The story card is rebuilt on one flat colour, so your background would be replaced and the logo and product would be cut out with some of it. Nothing has been sent to the model yet. You can start from a banner with a flat or simple background, or go on with a simplified version that is labelled as simplified.
            </p>
            <div className="row">
              <button type="button" className="btn" onClick={() => void readBanner(busyBackground, true)} disabled={busy}>
                Use a simplified flat-colour version
              </button>
              <button type="button" className="btn" onClick={() => setBusyBackground(null)} disabled={busy}>
                Choose another banner
              </button>
            </div>
          </div>
        </div>
      ) : null}
      {busy && reading ? (
        <div className="reading-panel">
          <Suspense fallback={null}>
            <ReadingLoader />
          </Suspense>
          <p className="status busy" role="status" aria-live="polite">
            {status}
          </p>
        </div>
      ) : (
        <p className={busy ? "status busy" : "status"} role="status" aria-live="polite">
          {busy ? status : ""}
        </p>
      )}
    </>
  );

  return (
    <main className="page adapt" id="stage">
      {step === 1 && door === "sketch" ? (
        <section aria-labelledby="s-title" className="sketchdoor">
          <h2 id="s-title" tabIndex={-1} ref={heading}>
            Start from a sketch
          </h2>
          <p className="lede">Draw boxes for the logo, the picture, the words and the button. Add your product page and the words come from it.</p>
          {notices}
          <div className="panel">
            <h3>1. Your sketch</h3>
            <p className="muted small">A photo or screenshot of a rough wireframe. It is letterboxed onto 16:9.</p>
            <div className="cta-row">
              <label className="btn primary filebtn">
                <UploadSimple size={18} weight="bold" aria-hidden="true" />
                Choose a sketch
                <input type="file" accept="image/png,image/jpeg" aria-label="Sketch image" disabled={busy || !wid} onChange={(e) => void onSketch(e.target.files?.[0])} />
              </label>
              <button type="button" className="btn" onClick={() => void sampleSketch()} disabled={busy || !wid}>
                Use the sample sketch
              </button>
            </div>
            <p className="muted small">The sample is a generated wireframe, not a hand drawing. A photo of your own sketch is the real test.</p>
            {sketchSrc ? <img className="sketch-preview" src={sketchSrc} alt="Your sketch" /> : null}
          </div>
          <div className="panel">
            <h3>2. Your product page (optional)</h3>
            <label className="field">
              <span className="visually-hidden">Product page address</span>
              <input type="url" placeholder="https://" value={pageUrl} onChange={(e) => setPageUrl(e.target.value)} disabled={busy} />
            </label>
            <p className="muted small">Tavily reads the page. Every number and name in the copy has to be on it. The address is sent to Tavily; the sketch image is sent to Nebius Token Factory.</p>
            <div className="cta-row">
              <button type="button" className="btn small" onClick={() => setPageUrl(samplePageUrl())} disabled={busy}>
                Use the sample page
              </button>
            </div>
          </div>
          <div className="cta-row">
            <button type="button" className="btn primary" onClick={() => void readSketch()} disabled={busy || !wid || !sketchSrc}>
              Read my sketch
            </button>
            <button type="button" className="btn quiet" onClick={() => setDoor("choose")} disabled={busy}>
              Back
            </button>
          </div>
        </section>
      ) : step === 1 ? (
        <section aria-labelledby="a-choose" className={over ? "hero-grid drop over" : "hero-grid drop"} onDragOver={(e) => { e.preventDefault(); setOver(true); }} onDragLeave={() => setOver(false)} onDrop={onDrop}>
          <div className="hero-copy">
            <h2 tabIndex={-1} ref={heading} className="display">
              {title}
            </h2>
            <p className="lede">Nemotron reads its parts, you check them, and every result is independently verified before you see it.</p>
            <h3 id="a-choose" className="visually-hidden">
              Choose a banner
            </h3>
            {notices}
            <div className="cta-row">
              <label className="btn primary filebtn">
                <UploadSimple size={18} weight="bold" aria-hidden="true" />
                Choose a banner
                <input type="file" accept="image/png,image/jpeg" disabled={busy || !wid} onChange={(e) => { const f = e.target.files?.[0]; e.target.value = ""; void onFile(f); }} />
              </label>
              <button type="button" className="btn" onClick={() => setDoor("sketch")} disabled={busy || !wid}>
                Start from a sketch
              </button>
              <span className="muted small">PNG or JPEG, 16:9. A photo of a rough sketch works too. Or drop a banner anywhere here.</span>
            </div>
            {samples.length ? (
              <div className="samples-row">
                <p className="label">Or start from a sample</p>
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
            <p className="privacy small">Your banner is sent to NVIDIA Nemotron on Nebius Token Factory to read its layers, and kept in server memory for 30 minutes. Fonts are replaced with Liberation Sans.</p>
          </div>
          <div className="hero-visual">
            <img className="hv-banner" src="/hero-banner.webp" width={1100} height={619} alt="A wide headphone banner for Halden with a headline, a price, a button and small print on a dark purple background" />
            <img className="hv-card" src="/hero-card.webp" width={563} height={1000} alt="The same banner adapted to a tall story card" />
          </div>
        </section>
      ) : (
        <>
          <h2 tabIndex={-1} ref={heading}>
            {title}
          </h2>
          {notices}
        </>
      )}

      {step === 1 ? (
        <ol className="who" aria-label="Who does what">
          <li>
            <strong>Nemotron-3.5-Super-VL</strong> reads your banner or sketch
          </li>
          <li>
            <strong>Tavily</strong> reads your product page, when you give one
          </li>
          <li>
            <strong>You</strong> check the parts
          </li>
          <li>
            <strong>Deterministic checks and an independent verifier</strong> decide
          </li>
          <li>
            <strong>Nemotron-3-Super</strong> words the question, and drafts copy from your page
          </li>
        </ol>
      ) : null}

      {step === 2 && upload && image ? (
        <section aria-labelledby="a-check">
          <h3 id="a-check" className="visually-hidden">
            Check the parts
          </h3>
          <div className={upload.origin === "model" ? "callout ok" : "callout"}>
            {upload.origin === "model" ? <CheckCircle size={22} weight="fill" aria-hidden="true" className="callout-icon" /> : null}
            <div>
            {upload.origin === "model" ? (
              <>
                <strong>Nemotron read this {kind === "sketch" ? "sketch" : "banner"}</strong> ({upload.model.replace(/^nvidia\//, "")}). {kind === "sketch" ? "Boxes are loose by design; drag them where you want each part, then continue." : "Boxes can be tight around the words; fix anything that is off, then continue."}
              </>
            ) : (
              <>
                <strong>Place the parts yourself.</strong> {sentence(upload.note || "No vision model answered")} Drag each box onto its part and type the words.
              </>
            )}
            {upload.problems.length ? (
              <ul>
                {upload.problems.map((p) => (
                  <li key={p}>{p}</li>
                ))}
              </ul>
            ) : null}
            </div>
          </div>
          {snapNote ? <p className="muted small">{snapNote}</p> : null}
          {overlaps.length ? (
            <div className="callout bad" role="alert">
              <strong>Fix before continuing:</strong>
              <ul>
                {overlaps.map((m) => (
                  <li key={m}>{m}</li>
                ))}
              </ul>
            </div>
          ) : null}
          {pageNote ? (
            <p className="callout" role="status">
              <WarningCircle size={22} weight="fill" aria-hidden="true" className="callout-icon" />
              <span>The page could not be read: {pageNote} Type the words yourself.</span>
            </p>
          ) : null}
          <LayerEditor
            image={image}
            layers={layers}
            onChange={setLayers}
            disabled={busy}
            lead={
              kind === "sketch" ? (
                <>
                  {page ? (
                    <CopyPanel
                      page={page}
                      choice={choice}
                      onChoice={onChoice}
                      price={priceLine}
                      onPrice={onPrice}
                      cta={ctaLabel}
                      onCta={onCta}
                      hasPrice={layers.some((l) => l.role === "price")}
                      hasCta={layers.some((l) => l.role === "cta")}
                      disabled={busy}
                    />
                  ) : null}
                  <PicturesPanel layers={layers} pics={pics} onPick={(r, f) => void pickPicture(r, f)} onSample={samplePictures} disabled={busy} />
                  <ColourPanel value={background} onChange={setBackground} disabled={busy} />
                </>
              ) : null
            }
          />
          {kind === "banner" ? <CropPreview img={imgEl.current} layers={layers} pix={pix.current} flat={flat} /> : null}
          <div className="lextras">
            {kind === "banner" ? (
              <>
                <button type="button" className="btn" onClick={snapAll} disabled={busy || !flat} title={flat ? undefined : "Only works on a flat background"}>
                  Snap boxes to the content
                </button>
                <label>
                  Background colour
                  <input type="color" value={hexOr(background, "#000000")} onChange={(e) => setBackground(e.target.value)} />
                </label>
                <label>
                  Check the price against your page (optional)
                  <input type="url" placeholder="https://" value={pageUrl} onChange={(e) => setPageUrl(e.target.value)} />
                </label>
              </>
            ) : null}
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
          <h3 id="a-result" className="visually-hidden">
            Your story cards
          </h3>
          <div className="trio">
            <figure>
              <img src={banner.original} alt={kind === "sketch" ? "Your sketch" : "Your banner"} />
              <figcaption>{kind === "sketch" ? "Your sketch" : "Your banner"}</figcaption>
            </figure>
            <span aria-hidden="true" className="arrow">
              <ArrowRight size={18} />
            </span>
            <figure>
              <img src={banner.rebuilt} alt="Your banner rebuilt as editable layers" />
              <figcaption>
                {kind === "sketch" ? "Your banner, built from the sketch" : flat ? "Rebuilt as editable layers" : "Rebuilt as editable layers. Your background is not a flat colour, so it is replaced by one flat colour: a simplified version, not a faithful one."}
              </figcaption>
            </figure>
            <span aria-hidden="true" className="arrow">
              <ArrowRight size={18} />
            </span>
            <figure className={finished ? "" : "pending"}>
              {run.result ? <img src={run.result.png} alt="The story card" /> : <div className="placeholder">{run.status === "question" ? "Waiting for your decision" : "No result yet"}</div>}
              <figcaption>{finished ? "Story card, 1080 × 1920" : "Story card"}</figcaption>
            </figure>
          </div>

          {run.status === "question" ? (
            <div className="question" aria-label="Question">
              <p>
                <strong>{run.previews.length > 0 && run.previews.every((p) => !p.fits) ? "No layout fits this banner, so it stopped instead of guessing." : "The copy does not fit, so it is asking instead of guessing."}</strong>{" "}
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
              {run.previews.length > 0 && run.previews.every((p) => !p.fits) ? (
                <div className="callout bad" role="alert">
                  <WarningCircle size={22} weight="fill" aria-hidden="true" className="callout-icon" />
                  <div>
                    <strong>Neither layout fits this banner, so nothing was built.</strong>
                    <ul>
                      {noFitReasons(run.previews).reasons.map((r) => (
                        <li key={r}>{r}.</li>
                      ))}
                    </ul>
                    {noFitReasons(run.previews).steps.map((s) => (
                      <p key={s}>{s}</p>
                    ))}
                  </div>
                </div>
              ) : (
                <button className="btn" onClick={() => void answer("neither")} disabled={busy}>
                  Neither: leave it unchanged
                </button>
              )}
            </div>
          ) : null}

          {run.status === "blocked" || run.status === "failed" || run.status === "unsupported_format" || run.status === "needs_roles" ? (
            <p className="callout bad" role="alert">
              <strong>Not applied.</strong> {run.problems.join("; ") || (verification ? `The independent verifier refused this result (failed: ${verification.failed.join(", ")}).` : "Something went wrong.")} Your banner is unchanged.
            </p>
          ) : null}
          {run.status === "unchanged" ? <p className="callout">Nothing was built and nothing was saved. Your banner is unchanged.</p> : null}

          {finished && verification ? (
            <>
              <div className="callout ok">
                <CheckCircle size={22} weight="fill" aria-hidden="true" className="callout-icon" />
                <div>
                  <strong>
                    {passed} of {verification.checks.length} checks passed
                  </strong>{" "}
                  <span className="small">
                    independent verifier: exact copy, link, logo, image proportions, safe areas, minimum sizes, text fit. It has no authored expected output for your banner, so that comparison is not part of these checks.
                  </span>
                  {run.preference ? (
                    <>
                      {" "}
                      <span className="pill ok">remembered for this workspace: {outcomeLabel(run.preference.outcome)} for {run.locale} (version {run.preference.version})</span>{" "}
                      <span className="small muted">Kept for about 30 minutes while the server runs; a reload or restart starts fresh.</span>
                    </>
                  ) : null}
                </div>
              </div>
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
              {finished && wid && run ? <ProofPanel wid={wid} runId={run.run_id} pageCheck={pageCheck} /> : null}
              {page || checkNote ? <PageCheckBox check={pageCheck} error={pageCheck ? "" : checkNote} /> : null}
              {kind === "sketch" && upload ? <Provenance model={upload.origin === "model" ? upload.model : ""} layers={layers} page={page} choice={choice} pics={pics} background={background} /> : null}
              <div className="controls">
                <a className="btn primary" href={run.result?.png} download="story-card.png">
                  <DownloadSimple size={18} weight="bold" aria-hidden="true" />
                  Download the story card (PNG)
                </a>
                {kind === "sketch" ? (
                  <a className="btn" href={banner.rebuilt} download="banner.png">
                    <DownloadSimple size={18} weight="bold" aria-hidden="true" />
                    Download the banner (PNG)
                  </a>
                ) : null}
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
          <li>The logo, the product image and the headline are required, and the product image must be larger than the logo. The price, the button and the small print are optional: remove any the banner does not have.</li>
          <li>Banners must be 16:9; one story-card layout (1080 × 1920) is learned from a single example.</li>
          <li>The logo and the product are cut out as rectangles, so their boxes must not overlap (a product whose rectangle reaches into the logo would carry a piece of it). A tall, narrow product, such as a bottle, cannot reach the minimum product width on a story card: the app says so and builds nothing.</li>
          <li>Nemotron can misplace or merge boxes, so you confirm every layer. The checks are structural: they do not look inside the pictures and cannot judge whether the result is beautiful.</li>
          <li>Measured so far: roles and words are read well; boxes are often loose or misplaced, most of all when the headline wraps onto many lines (see the evaluation in the repository). No people have been studied.</li>
        </ul>
      </details>
    </main>
  );
}
