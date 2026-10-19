import type { Provenance } from "./types";

export const provenanceLine = (p: Provenance): string =>
  `Model: ${p.model} · Teacher: ${p.teacher}` + (p.policy && p.policy !== "A" ? ` · Policy: ${p.policy}` : "");
