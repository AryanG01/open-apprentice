import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { KeyboardEvent, PointerEvent } from "react";
import { ApiError, get, post, url } from "./api";
import { fmt, frameFor, parseNum, snap64, step, toDisplay, type Point } from "./geometry";
import type { SceneView } from "./types";

export const SAFETY_LINE =
  "Previews are displayed in image context; uploaded content is separately validated and rendered in the locked engine.";

type Positions = Record<string, Point>;
type Draft = { png: string | null; image_offset: { x: string; y: string }; boxes: Record<string, { x: string; y: string }> };
type Landing = { seq: number; positions: Positions; offset: Point; measured: Draft["boxes"] };

type Props = {
  docId: string;
  pageId: string;
  mappingHash: string;
  editable: boolean;
  title: string;
  /** starting positions (document units) for some labels, e.g. a run's output */
  start?: Positions;
  /** moved labels and whether the user has seen the render of exactly these positions */
  onChange?: (moved: Positions, seen: boolean) => void;
  onScene?: (scene: SceneView) => void;
};

export function DocumentView({ docId, pageId, mappingHash, editable, title, start, onChange, onScene }: Props) {
  const [scene, setScene] = useState<SceneView | null>(null);
  const [src, setSrc] = useState<string>(url(`/documents/${docId}/pages/${pageId}/preview.png`));
  const [offset, setOffset] = useState<Point>({ x: 0, y: 0 });
  const [natural, setNatural] = useState(0);
  const [shown, setShown] = useState(0);
  const [pos, setPos] = useState<Positions>({});
  const [moved, setMoved] = useState<Positions>({});
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const img = useRef<HTMLImageElement | null>(null);
  const drag = useRef<{ id: string; x0: number; y0: number; p0: Point } | null>(null);
  const draftSeq = useRef(0);
  const landing = useRef<Landing | null>(null); // a draft whose image is loading; applied together on load
  const srcRef = useRef<string>("");
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);
  const startRef = useRef(start);
  const onChangeRef = useRef(onChange);
  onChangeRef.current = onChange; // parents may pass a new callback each render; never re-trigger renders because of it

  // scene geometry and the starting image
  useEffect(() => {
    const ctl = new AbortController();
    get<SceneView>(`/documents/${docId}/pages/${pageId}/scene?mapping_hash=${mappingHash}`, ctl.signal)
      .then((s) => {
        setScene(s);
        onScene?.(s);
        setOffset({ x: parseNum(s.image_offset.x), y: parseNum(s.image_offset.y) });
        const p: Positions = {};
        for (const o of s.objects) if (s.movable.includes(o.id)) p[o.id] = { x: parseNum(o.x), y: parseNum(o.y) };
        const st = startRef.current ?? {};
        setPos({ ...p, ...st });
        if (Object.keys(st).length) setMoved(st);
      })
      .catch((e) => {
        if (!(e instanceof DOMException && e.name === "AbortError")) setError(e instanceof ApiError ? e.message : String(e));
      });
    return () => ctl.abort();
  }, [docId, pageId, mappingHash]); // eslint-disable-line react-hooks/exhaustive-deps

  // the displayed width follows the layout (window resize, zoom)
  useEffect(() => {
    const el = img.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(() => setShown(el.clientWidth));
    ro.observe(el);
    return () => ro.disconnect();
  }, [scene]);

  // image, offset and geometry of a draft are applied together, only once its image is on screen (spec 8)
  const land = useCallback((l: Landing) => {
    setOffset(l.offset);
    const measured: Positions = {};
    for (const [k, b] of Object.entries(l.measured)) if (k in l.positions) measured[k] = { x: snap64(parseNum(b.x)), y: snap64(parseNum(b.y)) };
    const shownNow = { ...l.positions, ...measured };
    setPos((old) => ({ ...old, ...shownNow }));
    setMoved(shownNow);
    setPending(false);
    onChangeRef.current?.(shownNow, true);
  }, []);

  const requestDraft = useCallback(
    (next: Positions) => {
      if (timer.current) clearTimeout(timer.current);
      const seq = ++draftSeq.current; // every edit supersedes any render still in flight
      landing.current = null;
      setPending(true);
      onChangeRef.current?.(next, false);
      timer.current = setTimeout(async () => {
        if (seq !== draftSeq.current) return;
        const boxes: Record<string, [string, string]> = {};
        for (const [k, p] of Object.entries(next)) boxes[k] = [fmt(p.x), fmt(p.y)];
        try {
          const d = await post<Draft>(`/documents/${docId}/draft`, { page_id: pageId, mapping_hash: mappingHash, boxes });
          if (seq !== draftSeq.current) return; // a newer edit superseded this render
          if (!d.png) {
            setPending(false);
            setError("The engine returned no image for this edit; move the label again to retry.");
            return;
          }
          setError(null);
          const l: Landing = { seq, positions: next, offset: { x: parseNum(d.image_offset.x), y: parseNum(d.image_offset.y) }, measured: d.boxes };
          const nextSrc = `data:image/png;base64,${d.png}`;
          if (nextSrc === srcRef.current) {
            land(l); // the same image is already on screen: nothing new to load
          } else {
            landing.current = l;
            setSrc(nextSrc);
          }
        } catch (e) {
          if (seq === draftSeq.current) {
            setPending(false);
            setError(e instanceof ApiError ? e.message : String(e));
          }
        }
      }, 300);
    },
    [docId, pageId, mappingHash, land],
  );

  // a start position (e.g. a run's output) is rendered once so the user sees it before editing
  useEffect(() => {
    if (scene && startRef.current && Object.keys(startRef.current).length) requestDraft(startRef.current);
  }, [scene, requestDraft]);

  useEffect(() => () => clearTimeout(timer.current), []);

  const onImageLoad = () => {
    const el = img.current;
    if (!el) return;
    srcRef.current = el.getAttribute("src") ?? "";
    setNatural(el.naturalWidth);
    setShown(el.clientWidth);
    const l = landing.current;
    if (l !== null && l.seq === draftSeq.current) {
      landing.current = null;
      land(l);
    }
  };

  const frame = useMemo(() => frameFor(offset, natural, shown), [offset, natural, shown]);

  const place = (id: string, p: Point) => {
    const q = { x: snap64(p.x), y: snap64(p.y) };
    setPos((old) => ({ ...old, [id]: q }));
    const next = { ...moved, [id]: q };
    setMoved(next);
    requestDraft(next);
  };

  const onPointerDown = (id: string) => (e: PointerEvent<HTMLButtonElement>) => {
    setSelected(id);
    if (!editable) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    drag.current = { id, x0: e.clientX, y0: e.clientY, p0: pos[id] };
  };
  const onPointerMove = (e: PointerEvent<HTMLButtonElement>) => {
    const d = drag.current;
    if (!d) return;
    setPos((old) => ({ ...old, [d.id]: { x: d.p0.x + (e.clientX - d.x0) / frame.scale, y: d.p0.y + (e.clientY - d.y0) / frame.scale } }));
  };
  const onPointerUp = (e: PointerEvent<HTMLButtonElement>) => {
    const d = drag.current;
    drag.current = null;
    if (!d) return;
    const p = { x: d.p0.x + (e.clientX - d.x0) / frame.scale, y: d.p0.y + (e.clientY - d.y0) / frame.scale };
    if (p.x !== d.p0.x || p.y !== d.p0.y) place(d.id, p);
  };
  const onKey = (id: string) => (e: KeyboardEvent<HTMLButtonElement>) => {
    if (!editable) return;
    const s = step(e);
    const dir: Record<string, [number, number]> = { ArrowLeft: [-s, 0], ArrowRight: [s, 0], ArrowUp: [0, -s], ArrowDown: [0, s] };
    const v = dir[e.key];
    if (!v) return;
    e.preventDefault();
    place(id, { x: pos[id].x + v[0], y: pos[id].y + v[1] });
  };

  const labels = scene ? scene.objects.filter((o) => scene.movable.includes(o.id)) : [];

  return (
    <figure className="docview">
      {error ? <p className="err" role="alert">{error}</p> : null}
      <div className="docview-stage">
        <img ref={img} src={src} alt={title} onLoad={onImageLoad} draggable={false} />
        {natural > 0
          ? labels.map((o) => {
              const p = pos[o.id] ?? { x: parseNum(o.x), y: parseNum(o.y) };
              const b = toDisplay(frame, { x: p.x, y: p.y, w: parseNum(o.w), h: parseNum(o.h) });
              const isMoved = o.id in moved;
              return (
                <button
                  key={o.id}
                  type="button"
                  className={`lab${isMoved ? " moved" : ""}${selected === o.id ? " sel" : ""}`}
                  aria-label={`label ${o.id}`}
                  data-label={o.id}
                  style={{ left: b.x, top: b.y, width: b.w, height: b.h }}
                  onPointerDown={onPointerDown(o.id)}
                  onPointerMove={onPointerMove}
                  onPointerUp={onPointerUp}
                  onKeyDown={onKey(o.id)}
                  onFocus={() => setSelected(o.id)}
                >
                  {isMoved ? <span className="badge">moved</span> : null}
                </button>
              );
            })
          : null}
      </div>
      {editable && selected && pos[selected] ? (
        <div className="fields">
          <label>
            x of {selected}{" "}
            <input aria-label={`x of ${selected}`} type="number" step={1 / 64} value={pos[selected].x}
              onChange={(e) => place(selected, { x: Number(e.target.value), y: pos[selected].y })} />
          </label>
          <label>
            y of {selected}{" "}
            <input aria-label={`y of ${selected}`} type="number" step={1 / 64} value={pos[selected].y}
              onChange={(e) => place(selected, { x: pos[selected].x, y: Number(e.target.value) })} />
          </label>
          <span className="hint">Arrow = 1 unit · Shift = 10 · Alt = 1/64</span>
        </div>
      ) : null}
      <figcaption>
        {title}
        {pending ? <span className="pending" data-pending="1"> · rendering…</span> : null}
        <small className="safety">{SAFETY_LINE}</small>
      </figcaption>
    </figure>
  );
}
