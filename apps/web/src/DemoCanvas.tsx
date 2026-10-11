import { useRef, useState } from "react";

export interface Placement {
  inset_right: number;
  inset_top: number;
}

export const CARD_W = 150;
export const CARD_H = 80;
const BADGE = 20;
const PAD = 70;
const MIN = -60;
const MAX = 120;

const clamp = (n: number): number => Math.min(MAX, Math.max(MIN, Math.round(n)));

interface Props {
  value: Placement;
  onChange: (p: Placement) => void;
  disabled?: boolean;
}

/** Teach by doing: drag the badge (or use the number fields / arrow keys). The placement IS the demonstration. */
export function DemoCanvas({ value, onChange, disabled }: Props) {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const [drag, setDrag] = useState(false);
  const x = CARD_W - value.inset_right - BADGE;
  const y = value.inset_top;

  const toPlacement = (clientX: number, clientY: number): Placement | null => {
    const svg = svgRef.current;
    const ctm = svg?.getScreenCTM();
    if (!svg || !ctm) return null;
    const pt = svg.createSVGPoint();
    pt.x = clientX;
    pt.y = clientY;
    const p = pt.matrixTransform(ctm.inverse());
    return { inset_right: clamp(CARD_W - (p.x - BADGE / 2) - BADGE), inset_top: clamp(p.y - BADGE / 2) };
  };

  const onKey = (e: React.KeyboardEvent) => {
    const step = e.shiftKey ? 10 : 1;
    const d: Record<string, [number, number]> = { ArrowLeft: [1, 0], ArrowRight: [-1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] };
    const m = d[e.key];
    if (!m || disabled) return;
    e.preventDefault();
    onChange({ inset_right: clamp(value.inset_right + m[0] * step), inset_top: clamp(value.inset_top + m[1] * step) });
  };

  return (
    <section className="democanvas scene" aria-label="Demonstrate: place the badge">
      <svg
        ref={svgRef}
        viewBox={`${-PAD} ${-PAD / 2} ${CARD_W + 2 * PAD} ${CARD_H + PAD}`}
        role="group"
        aria-label={`Card with a badge ${value.inset_right} pixels from its right edge and ${value.inset_top} pixels from its top edge`}
        onPointerMove={(e) => {
          if (!drag || disabled) return;
          const p = toPlacement(e.clientX, e.clientY);
          if (p) onChange(p);
        }}
        onPointerUp={() => setDrag(false)}
        onPointerLeave={() => setDrag(false)}
      >
        <rect className="scene-bg" x={-PAD} y={-PAD / 2} width={CARD_W + 2 * PAD} height={CARD_H + PAD} />
        <rect className="box role-card" x={0} y={0} width={CARD_W} height={CARD_H} rx={2} strokeWidth={0.8} />
        <text className="box-label" x={CARD_W / 2} y={CARD_H / 2 + 14} fontSize={9} textAnchor="middle">card</text>
        <rect
          className={drag ? "box role-badge dragging" : "box role-badge draggable"}
          x={x}
          y={y}
          width={BADGE}
          height={BADGE}
          rx={2}
          strokeWidth={0.8}
          tabIndex={disabled ? -1 : 0}
          role="slider"
          aria-label="Badge. Drag it, or use the arrow keys (shift for bigger steps)."
          aria-valuetext={`${value.inset_right} from the right edge, ${value.inset_top} from the top`}
          onKeyDown={onKey}
          onPointerDown={(e) => {
            if (disabled) return;
            (e.target as Element).setPointerCapture?.(e.pointerId);
            setDrag(true);
          }}
        />
      </svg>
      <div className="demofields">
        <label>
          From the right edge (px)
          <input type="number" min={MIN} max={MAX} value={value.inset_right} disabled={disabled} onChange={(e) => onChange({ ...value, inset_right: clamp(Number(e.target.value)) })} />
        </label>
        <label>
          From the top edge (px)
          <input type="number" min={MIN} max={MAX} value={value.inset_top} disabled={disabled} onChange={(e) => onChange({ ...value, inset_top: clamp(Number(e.target.value)) })} />
        </label>
        <button type="button" disabled={disabled} onClick={() => onChange({ inset_right: 12, inset_top: 12 })}>Reset to the corner (12, 12)</button>
      </div>
      <p className="muted small">
        Put the badge in the top-right corner with equal gaps and the system can usually find a rule. Put it somewhere else, such as the middle of the top edge, to see what it does when no rule it
        knows fits: it should say so, not guess.
      </p>
    </section>
  );
}
