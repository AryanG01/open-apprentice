// Overlay geometry for the document view. The preview PNG is the engine's SVG at scale 1, so
// image pixel = document coordinate + offset; the displayed image may be scaled to fit.
export type Box = { x: number; y: number; w: number; h: number };
export type Point = { x: number; y: number };
export type Frame = { offsetX: number; offsetY: number; scale: number }; // doc → displayed px: (x + offset) * scale

export const frameFor = (offset: Point, naturalWidth: number, displayedWidth: number): Frame => ({
  offsetX: offset.x,
  offsetY: offset.y,
  scale: naturalWidth > 0 && displayedWidth > 0 ? displayedWidth / naturalWidth : 1,
});

export const toDisplay = (f: Frame, b: Box): Box => ({
  x: (b.x + f.offsetX) * f.scale,
  y: (b.y + f.offsetY) * f.scale,
  w: b.w * f.scale,
  h: b.h * f.scale,
});

export const toDoc = (f: Frame, px: number, py: number): Point => ({ x: px / f.scale - f.offsetX, y: py / f.scale - f.offsetY });

// spec 8 keys: arrow = 1 unit, Shift = 10, Alt = 1/64
export const step = (e: { shiftKey: boolean; altKey: boolean }): number => (e.altKey ? 1 / 64 : e.shiftKey ? 10 : 1);

export const snap64 = (v: number): number => Math.round(v * 64) / 64;

// multiples of 1/64 are exact binary fractions, so String() prints them exactly and the server parses them exactly
export const fmt = (v: number): string => String(snap64(v));

// the server sends exact rationals as "n/d" strings or integers
export const parseNum = (s: string | number): number => {
  if (typeof s === "number") return s;
  const [n, d] = s.split("/");
  return d === undefined ? Number(n) : Number(n) / Number(d);
};
