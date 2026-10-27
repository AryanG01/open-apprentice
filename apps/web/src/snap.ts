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

// ---- clean pictures: cut a picture out of a flat-background banner without its neighbours -----------------------------------
// The rebuilt banner crops the logo and the product as rectangles. A rectangle can hold a piece of something else (the wordmark's tail
// above a lamp) or cut the picture off (a box a third too short). Both are visible and neither is a checkable "structure", so they are
// fixed where the pixels are: label the connected ink once, give each picture the components that are really its own, and paint the
// rest of the rectangle with the background colour. Only for a flat background; nothing here guesses beyond the pixels.

const CELL = 3; // ink is labelled on 3 px cells: a 1280 x 720 banner is 427 x 240 cells
const BRIDGE = 2; // cells: ink closer than 6 px counts as one object (a lamp's arm, the gap inside a word)

export interface Components {
  cw: number;
  ch: number;
  label: Int32Array; // 0 = background, else component id (1-based)
  boxes: number[][]; // [x, y, w, h] in pixels of each component's ink, index = id - 1
  inkCount: number[]; // ink pixels per component
  cells: number[]; // labelled cells per component
}

/** Label the connected ink of a flat-background banner. */
export function inkComponents(p: Pixels, bg: Rgb): Components {
  const cw = Math.ceil(p.width / CELL), ch = Math.ceil(p.height / CELL);
  const cell = new Uint8Array(cw * ch);
  for (let y = 0; y < p.height; y++) {
    for (let x = 0; x < p.width; x++) if (d2(px(p, x, y), bg) > INK_DIST2) cell[Math.floor(y / CELL) * cw + Math.floor(x / CELL)] = 1;
  }
  const label = new Int32Array(cw * ch);
  const boxes: number[][] = [];
  const stack: number[] = [];
  let next = 0;
  for (let c0 = 0; c0 < cw * ch; c0++) {
    if (!cell[c0] || label[c0]) continue;
    next++;
    label[c0] = next;
    stack.push(c0);
    while (stack.length) {
      const c = stack.pop() as number;
      const cx = c % cw, cy = (c - cx) / cw;
      for (let dy = -BRIDGE; dy <= BRIDGE; dy++) {
        for (let dx = -BRIDGE; dx <= BRIDGE; dx++) {
          const nx = cx + dx, ny = cy + dy;
          if (nx < 0 || ny < 0 || nx >= cw || ny >= ch) continue;
          const n = ny * cw + nx;
          if (cell[n] && !label[n]) {
            label[n] = next;
            stack.push(n);
          }
        }
      }
    }
  }
  const x0 = new Array(next).fill(p.width), y0 = new Array(next).fill(p.height), x1 = new Array(next).fill(-1), y1 = new Array(next).fill(-1), inkCount = new Array(next).fill(0);
  for (let y = 0; y < p.height; y++) {
    for (let x = 0; x < p.width; x++) {
      const id = label[Math.floor(y / CELL) * cw + Math.floor(x / CELL)];
      if (!id || d2(px(p, x, y), bg) <= INK_DIST2) continue;
      const i = id - 1;
      inkCount[i]++;
      if (x < x0[i]) x0[i] = x;
      if (x > x1[i]) x1[i] = x;
      if (y < y0[i]) y0[i] = y;
      if (y > y1[i]) y1[i] = y;
    }
  }
  for (let i = 0; i < next; i++) boxes.push([x0[i], y0[i], x1[i] - x0[i] + 1, y1[i] - y0[i] + 1]);
  const cells = new Array(next).fill(0);
  for (let c = 0; c < label.length; c++) if (label[c]) cells[label[c] - 1]++;
  return { cw, ch, label, boxes, inkCount, cells };
}

const area = (b: number[]): number => b[2] * b[3];
function overlapArea(a: number[], b: number[]): number {
  const w = Math.min(a[0] + a[2], b[0] + b[2]) - Math.max(a[0], b[0]);
  const h = Math.min(a[1] + a[3], b[1] + b[3]) - Math.max(a[1], b[1]);
  return w > 0 && h > 0 ? w * h : 0;
}

/** The components that make up the picture the model boxed: every one with at least a third of its ink inside the model's box (so a
 *  picture the box cuts short is found whole), that is not a speck, and that does not belong to another layer's box. `others` are the
 *  other layers' boxes. */
export function pictureComponents(comps: Components, seed: number[], others: number[][]): number[] {
  // share of each component's cells that fall inside the model's box (a box that cuts a picture short still holds a good part of it)
  const inside = new Array(comps.boxes.length).fill(0);
  const c0 = Math.max(0, Math.floor(seed[0] / CELL)), c1 = Math.min(comps.cw - 1, Math.floor((seed[0] + seed[2]) / CELL));
  const r0 = Math.max(0, Math.floor(seed[1] / CELL)), r1 = Math.min(comps.ch - 1, Math.floor((seed[1] + seed[3]) / CELL));
  for (let r = r0; r <= r1; r++) for (let c = c0; c <= c1; c++) { const id = comps.label[r * comps.cw + c]; if (id) inside[id - 1]++; }
  const cand: number[] = [];
  comps.boxes.forEach((_, i) => {
    if (comps.inkCount[i] >= 40 && inside[i] / comps.cells[i] >= 0.2) cand.push(i);
  });
  const biggest = Math.max(1, ...cand.map((i) => comps.inkCount[i]));
  const out: number[] = [];
  for (const i of cand) {
    if (comps.inkCount[i] < 0.02 * biggest) continue; // a speck next to this picture
    const b = comps.boxes[i];
    // text and logos inside another layer's box are not this picture, unless this picture's seed holds most of the component
    const share = inside[i] / comps.cells[i];
    const foreign = others.some((o) => overlapArea(b, o) / area(b) > 0.7 && share < 0.7);
    if (!foreign) out.push(i + 1);
  }
  return out;
}

/** Bounding box of the chosen components, padded a little. */
export function unionBox(comps: Components, ids: number[], pad = 2): number[] | null {
  if (!ids.length) return null;
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  for (const id of ids) {
    const b = comps.boxes[id - 1];
    x0 = Math.min(x0, b[0]); y0 = Math.min(y0, b[1]); x1 = Math.max(x1, b[0] + b[2]); y1 = Math.max(y1, b[1] + b[3]);
  }
  return [Math.max(0, x0 - pad), Math.max(0, y0 - pad), x1 - x0 + 2 * pad, y1 - y0 + 2 * pad];
}

/** Pixels (in the picture's crop) that belong to some other object: to be painted with the background colour. Returns crop-local
 *  rows as [x, y, w, h] runs. `keep` are this picture's own component ids. */
export function foreignRuns(p: Pixels, comps: Components, crop: number[], keep: number[]): number[][] {
  const own = new Set(keep);
  const [cx, cy, cw, ch] = crop.map(Math.round);
  const runs: number[][] = [];
  for (let y = 0; y < ch; y++) {
    const gy = cy + y;
    if (gy < 0 || gy >= p.height) continue;
    let start = -1;
    for (let x = 0; x <= cw; x++) {
      const gx = cx + x;
      let foreign = false;
      if (x < cw && gx >= 0 && gx < p.width) {
        const id = comps.label[Math.floor(gy / CELL) * comps.cw + Math.floor(gx / CELL)];
        foreign = id > 0 && !own.has(id);
      }
      if (foreign && start < 0) start = x;
      if (!foreign && start >= 0) {
        runs.push([start, y, x - start, 1]);
        start = -1;
      }
    }
  }
  return runs;
}

/** Sides of `box` where ink of this picture touches the edge (the box would cut the picture off). */
export function clippedSides(p: Pixels, comps: Components, box: number[], keep: number[]): string[] {
  const own = new Set(keep);
  const [bx, by, bw, bh] = box.map(Math.round);
  const sides: string[] = [];
  const own1 = (x: number, y: number): boolean => {
    if (x < 0 || y < 0 || x >= p.width || y >= p.height) return false;
    return own.has(comps.label[Math.floor(y / CELL) * comps.cw + Math.floor(x / CELL)]);
  };
  const count = (pts: [number, number][]): number => pts.filter(([x, y]) => own1(x, y)).length;
  const col = (x: number): [number, number][] => Array.from({ length: bh }, (_, i) => [x, by + i]);
  const row = (y: number): [number, number][] => Array.from({ length: bw }, (_, i) => [bx + i, y]);
  const need = 4;
  // ink of the picture right at the edge, with the same picture's ink continuing just outside: it is cut off
  const cut = (inside: [number, number][], outside: [number, number][]): boolean => count(inside) >= need && count(outside) >= need;
  if (cut(col(bx), col(bx - 1 - CELL))) sides.push("left");
  if (cut(col(bx + bw - 1), col(bx + bw + CELL))) sides.push("right");
  if (cut(row(by), row(by - 1 - CELL))) sides.push("top");
  if (cut(row(by + bh - 1), row(by + bh + CELL))) sides.push("bottom");
  return sides;
}

/** Blocks of text: runs of rows with ink in `zone`, merged when the gap between two runs is under half the smaller of their heights
 *  (line spacing inside a paragraph), ignoring ink inside `exclude` boxes. Reading order, top to bottom. */
export function textBlocks(p: Pixels, bg: Rgb, zone: number[], exclude: number[][]): number[][] {
  const [zx, zy, zw, zh] = zone.map(Math.round);
  const x0 = clamp(zx, 0, p.width), x1 = clamp(zx + zw, 0, p.width), y0 = clamp(zy, 0, p.height), y1 = clamp(zy + zh, 0, p.height);
  const skip = (x: number, y: number): boolean => exclude.some((e) => x >= e[0] && x < e[0] + e[2] && y >= e[1] && y < e[1] + e[3]);
  const rowSpan: ([number, number] | null)[] = [];
  const rowCount: number[] = [];
  for (let y = y0; y < y1; y++) {
    let lo = -1, hi = -1, n = 0;
    for (let x = x0; x < x1; x++) {
      if (!skip(x, y) && d2(px(p, x, y), bg) > INK_DIST2) {
        if (lo < 0) lo = x;
        hi = x;
        n++;
      }
    }
    rowSpan.push(lo < 0 ? null : [lo, hi]);
    rowCount.push(n);
  }
  // a button plate is a solid slab (most of its box is ink); words are not. A slab never merges with the text above or below it.
  const solid = (a: number, b: number): boolean => {
    let lo = Infinity, hi = -Infinity, ink = 0;
    for (let i = a; i <= b; i++) {
      const s = rowSpan[i];
      if (s) {
        lo = Math.min(lo, s[0]);
        hi = Math.max(hi, s[1]);
      }
      ink += rowCount[i];
    }
    return b - a + 1 >= 24 && hi - lo >= 80 && ink / ((hi - lo + 1) * (b - a + 1)) > 0.6;
  };
  const runs: { a: number; b: number }[] = [];
  for (let i = 0; i < rowSpan.length; i++) {
    if (!rowSpan[i]) continue;
    const last = runs[runs.length - 1];
    if (last && last.b === i - 1) last.b = i;
    else runs.push({ a: i, b: i });
  }
  const merged: { a: number; b: number }[] = [];
  for (const r of runs) {
    const m = merged[merged.length - 1];
    if (m) {
      const gap = r.a - m.b - 1, small = Math.min(m.b - m.a + 1, r.b - r.a + 1);
      if (gap <= 0.5 * small && !solid(m.a, m.b) && !solid(r.a, r.b)) {
        m.b = r.b;
        continue;
      }
    }
    merged.push({ ...r });
  }
  return merged
    .map((r) => {
      let lo = x1, hi = x0;
      for (let i = r.a; i <= r.b; i++) {
        const s = rowSpan[i];
        if (s) {
          lo = Math.min(lo, s[0]);
          hi = Math.max(hi, s[1]);
        }
      }
      return [Math.max(0, lo - PAD), y0 + r.a - PAD, hi - lo + 1 + 2 * PAD, r.b - r.a + 1 + 2 * PAD];
    })
    .filter((b) => b[2] * b[3] >= 60);
}

const TEXT_ORDER = ["headline", "price", "cta", "legal"];

/** When the model's text boxes disagree with the pixels (a headline that wrapped onto five lines pushed the price, button and small
 *  print onto its last lines), put each text box on the block it belongs to, but only when the blocks found are exactly as many as
 *  the text parts and read top to bottom in the usual order. Otherwise null: nothing is moved on a guess. */
export function reassignText(p: Pixels, bg: Rgb, layers: { role: string; box: number[] }[], keepOut: number[][]): { role: string; box: number[] }[] | null {
  const texts = TEXT_ORDER.map((r) => layers.find((l) => l.role === r)).filter((l): l is { role: string; box: number[] } => !!l);
  if (texts.length < 2) return null;
  const left = Math.min(...texts.map((t) => t.box[0])) - 30;
  // the pictures' real extents (the model's picture boxes are often too small, and a bottle's edge would look like a text block)
  const comps = inkComponents(p, bg);
  const imgs = layers.filter((l) => l.role === "brand_mark" || l.role === "product_image");
  const fitted = imgs.map((l) => unionBox(comps, pictureComponents(comps, l.box, imgs.filter((o) => o !== l).map((o) => o.box)), 2) ?? l.box);
  const blocks = textBlocks(p, bg, [Math.max(0, left), 0, p.width, p.height], [...keepOut, ...fitted]);
  if (blocks.length !== texts.length) return null;
  const moved = texts.map((t, i) => ({ role: t.role, box: blocks[i] })); // measured from the pixels, so tighter than any guess
  const byRole = new Map(moved.map((m) => [m.role, m.box]));
  return layers.map((l) => (byRole.has(l.role) ? { role: l.role, box: byRole.get(l.role) as number[] } : l));
}
