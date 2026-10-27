// "Snap to the content": a vision model's boxes are often too narrow or too loose, and pixels are the one thing we can measure
// exactly. On a flat background, grow the box while there is ink just outside it (bridging the small gaps between words and
// lines), then tighten it to the ink. Nothing here guesses: if the background is not flat, the box touches too much, or no ink
// is near, the box is returned unchanged. No imports on purpose: it is tested directly under Node.

export interface Pixels {
  data: Uint8ClampedArray | number[];
  width: number;
  height: number;
}
export type Rgb = [number, number, number];

const INK_DIST2 = 60 * 60; // squared RGB distance from the background beyond which a pixel counts as content
const FLAT_DIST2 = 40 * 40;
const PAD = 2;

const clamp = (v: number, lo: number, hi: number): number => Math.min(hi, Math.max(lo, v));
const median = (v: number[]): number => [...v].sort((a, b) => a - b)[Math.floor(v.length / 2)] ?? 0;

function px(p: Pixels, x: number, y: number): Rgb {
  const i = (y * p.width + x) * 4;
  return [p.data[i], p.data[i + 1], p.data[i + 2]];
}
const d2 = (a: Rgb, b: Rgb): number => (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2;

/** The background colour (median of the border) and whether the border is flat enough to trust it. */
export function backgroundOf(p: Pixels): { rgb: Rgb; flat: boolean } {
  const pts: [number, number][] = [];
  for (let x = 0; x < p.width; x += 4) pts.push([x, 2], [x, p.height - 3]);
  for (let y = 0; y < p.height; y += 4) pts.push([2, y], [p.width - 3, y]);
  const cols = pts.map(([x, y]) => px(p, x, y));
  const rgb: Rgb = [median(cols.map((c) => c[0])), median(cols.map((c) => c[1])), median(cols.map((c) => c[2]))];
  const near = cols.filter((c) => d2(c, rgb) <= FLAT_DIST2).length;
  return { rgb, flat: near / cols.length >= 0.92 };
}

/** Grow `box` ([x, y, w, h] in pixels) to the content it sits on, then tighten it. */
export function snapBox(p: Pixels, box: number[], bg: Rgb, opts: { flat?: boolean; maxGrow?: number } = {}): number[] {
  const original = [...box];
  if (opts.flat === false || box.length !== 4) return original;
  const [bx, by, bw, bh] = box;
  let L = clamp(Math.round(bx), 0, p.width - 1);
  let T = clamp(Math.round(by), 0, p.height - 1);
  let R = clamp(Math.round(bx + bw), L + 1, p.width); // exclusive
  let B = clamp(Math.round(by + bh), T + 1, p.height);
  const w0 = R - L, h0 = B - T;
  const grow = opts.maxGrow ?? Infinity; // images: the model is mostly right about them, so they may only grow a little
  const minL = Math.max(0, L - grow), minT = Math.max(0, T - grow), maxR = Math.min(p.width, R + grow), maxB = Math.min(p.height, B + grow);
  const gap = clamp(Math.round(0.5 * h0), 8, 24);
  const ink = (x: number, y: number): boolean => d2(px(p, x, y), bg) > INK_DIST2;
  const rowInk = (y: number, a: number, b: number): boolean => {
    for (let x = a; x < b; x++) if (ink(x, y)) return true;
    return false;
  };
  const colInk = (x: number, a: number, b: number): boolean => {
    for (let y = a; y < b; y++) if (ink(x, y)) return true;
    return false;
  };

  for (let guard = 0, changed = true; changed && guard < 4000; guard++) {
    changed = false;
    for (let k = 1; k <= gap && T - k >= minT; k++) if (rowInk(T - k, L, R)) { T -= k; changed = true; break; }
    for (let k = 0; k < gap && B + k < maxB; k++) if (rowInk(B + k, L, R)) { B += k + 1; changed = true; break; }
    for (let k = 1; k <= gap && L - k >= minL; k++) if (colInk(L - k, T, B)) { L -= k; changed = true; break; }
    for (let k = 0; k < gap && R + k < maxR; k++) if (colInk(R + k, T, B)) { R += k + 1; changed = true; break; }
    if (R - L > 3 * w0 + 80 || B - T > 3 * h0 + 60) return original; // it is leaking into something that is not this layer
  }

  let x0 = R, y0 = B, x1 = L, y1 = T;
  for (let y = T; y < B; y++) {
    for (let x = L; x < R; x++) {
      if (!ink(x, y)) continue;
      if (x < x0) x0 = x;
      if (x > x1) x1 = x;
      if (y < y0) y0 = y;
      if (y > y1) y1 = y;
    }
  }
  if (x1 < x0 || y1 < y0) return original; // no content here
  const sx = Math.max(0, x0 - PAD), sy = Math.max(0, y0 - PAD);
  return [sx, sy, Math.min(p.width, x1 + 1 + PAD) - sx, Math.min(p.height, y1 + 1 + PAD) - sy];
}

const NAME: Record<string, string> = { brand_mark: "Logo", product_image: "Product image", headline: "headline", price: "price", cta: "button", legal: "small print" };
const MAX_IMAGE_SHARE = 0.15; // mirrors campaign/vision.py: the server applies the same rule when the layers are confirmed
const MAX_TEXT_SHARE = 0.2;

/** Image boxes whose crop would hold words: by the image's share of the overlap, or by the text box's share. */
export function imageTextOverlaps(layers: { role: string; box: number[] }[]): string[] {
  const out: string[] = [];
  const area = (b: number[]): number => b[2] * b[3];
  for (const img of layers.filter((l) => l.role === "brand_mark" || l.role === "product_image")) {
    for (const t of layers.filter((l) => ["headline", "price", "cta", "legal"].includes(l.role))) {
      const w = Math.min(img.box[0] + img.box[2], t.box[0] + t.box[2]) - Math.max(img.box[0], t.box[0]);
      const h = Math.min(img.box[1] + img.box[3], t.box[1] + t.box[3]) - Math.max(img.box[1], t.box[1]);
      const shared = w > 0 && h > 0 ? w * h : 0;
      if (shared > 0 && (shared / area(img.box) > MAX_IMAGE_SHARE || shared / area(t.box) > MAX_TEXT_SHARE)) {
        out.push(`${NAME[img.role]} box overlaps the ${NAME[t.role]} text: its crop would contain words`);
      }
    }
  }
  const logo = layers.find((l) => l.role === "brand_mark");
  const product = layers.find((l) => l.role === "product_image");
  if (logo && product) {
    const w = Math.min(logo.box[0] + logo.box[2], product.box[0] + product.box[2]) - Math.max(logo.box[0], product.box[0]);
    const h = Math.min(logo.box[1] + logo.box[3], product.box[1] + product.box[3]) - Math.max(logo.box[1], product.box[1]);
    if (w > 0 && h > 0 && (w * h) / area(logo.box) > MAX_TEXT_SHARE) out.push("Product image box overlaps the logo: its crop would contain part of the logo");
  }
  return out;
}
