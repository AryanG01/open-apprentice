import type { Box, CanvasView } from "./types";

export interface Frame {
  x: number;
  y: number;
  w: number;
  h: number;
}

const PAD = 36;

/** One shared frame for every panel of a step, so side-by-side pictures are on the same scale. */
export function frameOf(views: CanvasView[]): Frame {
  // The clone prototype sits far from the card; framing it would shrink everything that matters.
  const boxes = views.flatMap((v) => v.boxes).filter((b) => b.role !== "prototype");
  if (boxes.length === 0) return { x: 0, y: 0, w: 400, h: 300 };
  const x0 = Math.min(...boxes.map((b) => b.x));
  const y0 = Math.min(...boxes.map((b) => b.y));
  const x1 = Math.max(...boxes.map((b) => b.x + b.w));
  const y1 = Math.max(...boxes.map((b) => b.y + b.h));
  return { x: x0 - PAD, y: y0 - PAD, w: x1 - x0 + 2 * PAD, h: y1 - y0 + 2 * PAD };
}

/** A tight frame around every box of one role plus the card's top-right corner they are measured from. */
export function zoomFrame(views: CanvasView[], role: string, pad: number): Frame {
  const boxes = views.flatMap((v) => v.boxes).filter((b) => b.role === role);
  if (boxes.length === 0) return frameOf(views);
  const corners = views.flatMap((v) => v.boxes).filter((b) => b.role === "card").map((c) => ({ x: c.x + c.w, y: c.y }));
  const xs = [...boxes.flatMap((b) => [b.x, b.x + b.w]), ...corners.map((c) => c.x)];
  const ys = [...boxes.flatMap((b) => [b.y, b.y + b.h]), ...corners.map((c) => c.y)];
  const x0 = Math.min(...xs);
  const y0 = Math.min(...ys);
  return { x: x0 - pad, y: y0 - pad, w: Math.max(...xs) - x0 + 2 * pad, h: Math.max(...ys) - y0 + 2 * pad };
}

const LAYER: Record<string, number> = { card: 0, object: 1, prototype: 2, badge: 3 };

const fmt = (n: number): string => (Math.round(n * 100) / 100).toString();

export function describeBox(b: Box): string {
  return `${b.id} (${b.role}): left ${fmt(b.x)}, top ${fmt(b.y)}, ${fmt(b.w)} by ${fmt(b.h)}`;
}

interface SceneProps {
  view: CanvasView;
  frame: Frame;
  ghost?: Box[];
  caption?: string;
  compact?: boolean;
}

/** Offset of each badge from its ghost (expected) box, in scene units. */
function offsets(view: CanvasView, ghost: Box[] | undefined): { id: string; dx: number; dy: number }[] {
  if (!ghost) return [];
  return view.boxes
    .map((b) => {
      const g = ghost.find((x) => x.id === b.id);
      return g ? { id: b.id, dx: b.x - g.x, dy: b.y - g.y } : null;
    })
    .filter((o): o is { id: string; dx: number; dy: number } => o !== null && (Math.abs(o.dx) > 0.01 || Math.abs(o.dy) > 0.01));
}

export function Scene({ view, frame, ghost, caption, compact }: SceneProps) {
  const off = offsets(view, ghost);
  const inView = (b: Box): boolean => b.x + b.w > frame.x && b.x < frame.x + frame.w && b.y + b.h > frame.y && b.y < frame.y + frame.h;
  const drawn = [...view.boxes].filter(inView).sort((a, b) => (LAYER[a.role] ?? 1) - (LAYER[b.role] ?? 1));
  const sw = Math.max(frame.w, frame.h) / 260;
  const fs = Math.max(frame.w, frame.h) / (compact ? 22 : 30);
  const title = `${view.label}. ${view.boxes.map(describeBox).join("; ")}`;
  return (
    <figure className={compact ? "scene compact" : "scene"}>
      <svg viewBox={`${frame.x} ${frame.y} ${frame.w} ${frame.h}`} role="img" aria-label={title} preserveAspectRatio="xMidYMid meet">
        <rect className="scene-bg" x={frame.x} y={frame.y} width={frame.w} height={frame.h} />
        {ghost?.map((g) => (
          <rect key={`g-${g.id}`} className="ghost" x={g.x} y={g.y} width={g.w} height={g.h} strokeWidth={sw * 1.2} strokeDasharray={`${sw * 4} ${sw * 3}`} />
        ))}
        {drawn.map((b) => (
          <g key={b.id}>
            <rect className={`box role-${b.role}`} x={b.x} y={b.y} width={b.w} height={b.h} strokeWidth={sw} rx={sw * 2} />
            {b.w > fs * 4 ? (
              <text className="box-label" x={b.x + b.w / 2} y={b.y + b.h / 2} fontSize={fs} textAnchor="middle" dominantBaseline="central">
                {b.role === "card" ? "card" : b.role === "prototype" ? "proto" : b.id}
              </text>
            ) : null}
          </g>
        ))}
        {off.map((o) => {
          const b = view.boxes.find((x) => x.id === o.id);
          if (!b) return null;
          return (
            <text key={`o-${o.id}`} className="offset-label" x={b.x + b.w / 2} y={b.y - fs * 0.6} fontSize={fs} textAnchor="middle">
              {`off by ${fmt(o.dx)}, ${fmt(o.dy)}`}
            </text>
          );
        })}
      </svg>
      <figcaption>
        <strong>{view.label}</strong>
        {caption ? <span> · {caption}</span> : null}
        {view.boxes.some((b) => b.role === "badge") ? <span className="legend-inline"> · <span className="swatch badge" aria-hidden="true" /> green square = badge</span> : null}
        {off.length > 0 ? <span className="fail-text"> · differs from expected</span> : ghost ? <span className="ok-text"> · matches expected</span> : null}
        <details>
          <summary>Text equivalent</summary>
          <ul>
            {view.boxes.map((b) => (
              <li key={b.id}>{describeBox(b)}</li>
            ))}
          </ul>
        </details>
      </figcaption>
    </figure>
  );
}
