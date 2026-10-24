import { useRef, useState } from "react";
import type { KeyboardEvent, PointerEvent } from "react";
import type { AdaptLayer } from "./types";

export const BANNER_W = 1280;
export const BANNER_H = 720;
export const ORDER = ["brand_mark", "product_image", "headline", "price", "cta", "legal"] as const;
export const LABEL: Record<string, string> = {
  brand_mark: "Logo",
  product_image: "Product image",
  headline: "Headline",
  price: "Price",
  cta: "Button",
  legal: "Small print",
};
const IMAGE_ROLES = new Set(["brand_mark", "product_image"]);
const MIN_SIDE = 24;
const HEX = /^#[0-9a-fA-F]{6}$/;

export const isImageRole = (role: string): boolean => IMAGE_ROLES.has(role);
export const hexOr = (v: string, fallback: string): string => (HEX.test(v) ? v : fallback);

const clamp = (v: number, lo: number, hi: number): number => Math.min(hi, Math.max(lo, v));

/** A starting box for a layer the model did not find: the owner drags it onto the right place. */
export function defaultLayer(role: string): AdaptLayer {
  const box = IMAGE_ROLES.has(role) ? [80, 152, 400, 400] : role === "cta" ? [640, 432, 256, 76] : [640, 160, 576, 120];
  return { role, box, text: "", font_px: role === "legal" ? 16 : role === "headline" ? 48 : 32, bold: role !== "legal", color: "", fill: "" };
}

type Drag = { role: string; mode: "move" | "resize"; x0: number; y0: number; box: number[] };

interface Props {
  image: string;
  layers: AdaptLayer[];
  onChange: (layers: AdaptLayer[]) => void;
  disabled?: boolean;
}

/** The banner with one draggable box per part, and a plain form for each. Everything is keyboard-operable: arrow keys move
 *  the focused box by 4 px, Shift+arrows resize it, Alt makes the step 1 px. */
export function LayerEditor({ image, layers, onChange, disabled }: Props) {
  const stage = useRef<HTMLDivElement>(null);
  const drag = useRef<Drag | null>(null);
  const [sel, setSel] = useState<string>("headline");
  const byRole = (role: string): AdaptLayer | undefined => layers.find((l) => l.role === role);

  const patch = (role: string, change: Partial<AdaptLayer>) => onChange(layers.map((l) => (l.role === role ? { ...l, ...change } : l)));
  const setBox = (role: string, box: number[]) => {
    const [x, y, w, h] = box;
    const cw = clamp(w, MIN_SIDE, BANNER_W);
    const ch = clamp(h, MIN_SIDE, BANNER_H);
    patch(role, { box: [clamp(x, 0, BANNER_W - cw), clamp(y, 0, BANNER_H - ch), cw, ch].map((v) => Math.round(v)) });
  };

  const start = (e: PointerEvent<HTMLElement>, role: string, mode: Drag["mode"]) => {
    const l = byRole(role);
    if (!l || disabled) return;
    e.preventDefault();
    e.stopPropagation();
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    setSel(role);
    drag.current = { role, mode, x0: e.clientX, y0: e.clientY, box: [...l.box] };
  };
  const move = (e: PointerEvent<HTMLElement>) => {
    const d = drag.current;
    const rect = stage.current?.getBoundingClientRect();
    if (!d || !rect) return;
    const k = BANNER_W / rect.width;
    const dx = (e.clientX - d.x0) * k;
    const dy = (e.clientY - d.y0) * k;
    const [x, y, w, h] = d.box;
    setBox(d.role, d.mode === "move" ? [x + dx, y + dy, w, h] : [x, y, w + dx, h + dy]);
  };
  const end = () => {
    drag.current = null;
  };
  const key = (e: KeyboardEvent<HTMLElement>, role: string) => {
    const l = byRole(role);
    const dir: Record<string, [number, number]> = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] };
    if (!l || disabled || !dir[e.key]) return;
    e.preventDefault();
    const step = e.altKey ? 1 : 4;
    const [dx, dy] = dir[e.key];
    const [x, y, w, h] = l.box;
    setBox(role, e.shiftKey ? [x, y, w + dx * step, h + dy * step] : [x + dx * step, y + dy * step, w, h]);
  };

  return (
    <div className="editor">
      <div className="lstage" ref={stage} style={{ aspectRatio: `${BANNER_W} / ${BANNER_H}` }}>
        <img src={image} alt="Your banner" draggable={false} />
        {ORDER.map((role) => {
          const l = byRole(role);
          if (!l) return null;
          const [x, y, w, h] = l.box;
          return (
            <div
              key={role}
              role="group"
              tabIndex={0}
              className={sel === role ? `lbox on r-${role}` : `lbox r-${role}`}
              aria-label={`${LABEL[role]} box. Arrow keys move it, Shift plus arrow keys resize it.`}
              style={{ left: `${(x / BANNER_W) * 100}%`, top: `${(y / BANNER_H) * 100}%`, width: `${(w / BANNER_W) * 100}%`, height: `${(h / BANNER_H) * 100}%` }}
              onFocus={() => setSel(role)}
              onPointerDown={(e) => start(e, role, "move")}
              onPointerMove={move}
              onPointerUp={end}
              onPointerCancel={end}
              onKeyDown={(e) => key(e, role)}
            >
              <span className="ltag">{LABEL[role]}</span>
              <span
                className="lhandle"
                aria-hidden="true"
                onPointerDown={(e) => start(e, role, "resize")}
                onPointerMove={move}
                onPointerUp={end}
                onPointerCancel={end}
              />
            </div>
          );
        })}
      </div>
      <p className="muted small" id="editor-help">
        Drag a box to move it, drag its corner to resize it. With the keyboard: arrow keys move the focused box, Shift plus arrows resize it.
      </p>

      <div className="lfields">
        {ORDER.map((role) => {
          const l = byRole(role);
          if (!l) {
            return (
              <fieldset key={role} className="lrow missing">
                <legend>{LABEL[role]}</legend>
                <p>Not found in the banner.</p>
                <button type="button" className="btn" disabled={disabled} onClick={() => onChange([...layers, defaultLayer(role)])}>
                  Add a {LABEL[role].toLowerCase()} box
                </button>
              </fieldset>
            );
          }
          const text = !isImageRole(role);
          return (
            <fieldset key={role} className={sel === role ? "lrow on" : "lrow"} onFocus={() => setSel(role)} disabled={disabled}>
              <legend>{LABEL[role]}</legend>
              {text ? (
                role === "headline" || role === "legal" ? (
                  <label>
                    Words in the image
                    <textarea rows={role === "legal" ? 3 : 2} value={l.text} onChange={(e) => patch(role, { text: e.target.value })} />
                  </label>
                ) : (
                  <label>
                    {role === "cta" ? "Button label" : "Words in the image"}
                    <input type="text" value={l.text} onChange={(e) => patch(role, { text: e.target.value })} />
                  </label>
                )
              ) : null}
              <div className="lnums">
                {(["x", "y", "width", "height"] as const).map((name, i) => (
                  <label key={name}>
                    {name === "x" ? "Left" : name === "y" ? "Top" : name === "width" ? "Width" : "Height"}
                    <input
                      type="number"
                      min={0}
                      step={1}
                      value={Math.round(l.box[i])}
                      onChange={(e) => {
                        const next = [...l.box];
                        next[i] = Number(e.target.value);
                        setBox(role, next);
                      }}
                    />
                  </label>
                ))}
                {text ? (
                  <>
                    <label>
                      Size (px)
                      <input type="number" min={6} max={400} step={1} value={Math.round(l.font_px)} onChange={(e) => patch(role, { font_px: Number(e.target.value) })} />
                    </label>
                    <label className="inline">
                      <input type="checkbox" checked={l.bold} onChange={(e) => patch(role, { bold: e.target.checked })} /> Bold
                    </label>
                    <label>
                      {role === "cta" ? "Label colour" : "Text colour"}
                      <input type="color" value={hexOr(l.color, "#ffffff")} onChange={(e) => patch(role, { color: e.target.value })} />
                    </label>
                  </>
                ) : null}
                {role === "cta" ? (
                  <label>
                    Button colour
                    <input type="color" value={hexOr(l.fill, "#ffd23f")} onChange={(e) => patch(role, { fill: e.target.value })} />
                  </label>
                ) : null}
              </div>
            </fieldset>
          );
        })}
      </div>
    </div>
  );
}
