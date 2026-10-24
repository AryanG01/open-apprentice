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
export function snapBox(p: Pixels, box: number[], bg: Rgb, opts: { flat?: boolean } = {}): number[] {
  const original = [...box];
  if (opts.flat === false || box.length !== 4) return original;
  const [bx, by, bw, bh] = box;
  let L = clamp(Math.round(bx), 0, p.width - 1);
  let T = clamp(Math.round(by), 0, p.height - 1);
  let R = clamp(Math.round(bx + bw), L + 1, p.width); // exclusive
  let B = clamp(Math.round(by + bh), T + 1, p.height);
  const w0 = R - L, h0 = B - T;
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
    for (let k = 1; k <= gap && T - k >= 0; k++) if (rowInk(T - k, L, R)) { T -= k; changed = true; break; }
    for (let k = 0; k < gap && B + k < p.height; k++) if (rowInk(B + k, L, R)) { B += k + 1; changed = true; break; }
    for (let k = 1; k <= gap && L - k >= 0; k++) if (colInk(L - k, T, B)) { L -= k; changed = true; break; }
    for (let k = 0; k < gap && R + k < p.width; k++) if (colInk(R + k, T, B)) { R += k + 1; changed = true; break; }
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
