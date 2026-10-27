// Why no layout fits, in plain words (from the measured violations), and what the owner can do. No imports: tested directly under Node.

export interface Violation {
  kind: string;
  node_id: string;
}
export interface PreviewLike {
  fits: boolean;
  violations: Violation[];
}

const PART: Record<string, string> = { product: "the product picture", headline: "the headline", price: "the price", cta: "the button", legal: "the small print", logo: "the logo" };
const WHAT: Record<string, string> = {
  below_minimum: "is smaller than the smallest size allowed on a story card",
  text_overflow: "does not fit in its frame",
  outside_safe: "would sit outside the safe area",
  overlap: "would overlap another part",
};
/** Why no layout fits, in plain words (from the measured violations), and what the owner can do. Never blames the owner's choice. */
export function noFitReasons(previews: PreviewLike[]): { reasons: string[]; steps: string[] } {
  const seen = new Set<string>();
  const reasons: string[] = [];
  const steps = new Set<string>();
  for (const p of previews) {
    for (const v of p.violations) {
      const part = Object.keys(PART).find((k) => String(v.node_id).toLowerCase().endsWith(`-${k}`) || String(v.node_id).toLowerCase().includes(k)) ?? "a part";
      const line = `${PART[part] ?? "a part"} ${WHAT[v.kind] ?? v.kind.replace(/_/g, " ")}`;
      if (!seen.has(line)) { seen.add(line); reasons.push(line); }
      if (v.kind === "below_minimum" && part === "product") steps.add("Use a banner where the product is larger, or cut the product picture tighter in the editor.");
      else if (v.kind === "text_overflow") steps.add("Your approved words are kept as they are, so the app will not shorten them; use a banner with less text or a larger text frame.");
      else steps.add("Move or resize that part in the editor and try again.");
    }
  }
  return { reasons, steps: [...steps] };
}

