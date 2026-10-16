// Response shapes of /api/v2 (numbers are exact rationals sent as strings).
export type Num = string;

export type Provenance = { model: "Live" | "Recorded" | "Fixture"; teacher: "You" | "Simulated" };

export type PageInfo = {
  page_id: string;
  index: number;
  name: string;
  status: "ok" | "refused";
  reason?: string;
  movable?: string[];
  fixed?: string[];
  reasons?: Record<string, string>;
  mapping: { labels: Record<string, { node_id: string; role: string }>; proposed: string[]; confirmed: boolean } | null;
  mapping_hash: string | null;
  scene_hash: string | null;
};

export type DocumentInfo = {
  doc_id: string;
  name: string;
  doc_hash: string;
  render: "pending" | "done" | "failed";
  render_error?: string;
  pages: PageInfo[];
};

export type DocRef = { doc_id: string; page_id: string; mapping_hash: string };

export type SceneObject = { id: string; kind: "node" | "label" | "obstacle"; role: string; attached: string; x: Num; y: Num; w: Num; h: Num };

export type SceneView = {
  scene_hash: string;
  canvas: { w: Num; h: Num };
  image_offset: { x: Num; y: Num };
  objects: SceneObject[];
  movable: string[];
};

export type Output = Record<string, [Num | number, Num | number]>;

export type Request =
  | { type: "ChooseOutput"; request_id: string; scene_id: string; scene_hash: string; alternatives: [string, Output][] }
  | { type: "ConfirmPreview"; request_id: string; purpose: string; items: [string, string, string, Output][] }
  | {
      type: "ConfirmCorrectionScope";
      request_id: string;
      interpretations: { interp_id: string; kind: "revise" | "override" | "accidental"; selector: string | null; summary: string; consequences: [string, string, Output][] }[];
    };

export type Check = { ok: boolean; reasons: string[] };

export type Outstanding = {
  request_id: string;
  intent_revision: number;
  request: Request;
  item_ids: string[];
  checks: Record<string, Check>;
  approve_all_answer: Record<string, unknown>;
};

export type SessionState = {
  session_id: string;
  kind: "teaching" | "correction";
  state: string;
  outstanding: Outstanding | null;
  budgets: Record<string, number>;
  spend: { recorded: Num; reserved: Num; uncertain: Num };
  manifest_revision: number;
  provenance: Provenance;
  result: { skill_id?: string; version?: number; activated?: boolean; reason?: string };
};

export type Receipt = {
  published: boolean;
  conformance: { ok: boolean; labels: Record<string, { ok: boolean; exact: Num[]; serialized: number[]; measured: Num[] }> };
  preservation: { ok: boolean; differences: string[] };
  layout: { ok: boolean; outside: string[]; overlaps: string[][] };
  intent: Record<string, unknown> | null;
  notes: string[];
};

export type RunResult = { status: "published" | "blocked" | "unchanged" | "failed"; reasons: string[]; receipt?: Receipt; key?: string };

export type RunInfo = {
  run_id: string;
  skill_id: string;
  version: number;
  status: "running" | "done" | "cancelled" | "failed";
  documents: DocRef[];
  results: Record<string, RunResult>;
  provenance: Provenance;
};

export type SkillInfo = {
  skill_id: string;
  active: { version: number | null; generation: number | null };
  versions: { version: number; parent_version: number | null; summary: string }[];
  provenance: Provenance | null;
};

export type Config = { live_available: boolean; model: string; max_upload_bytes: number };

export const TERMINAL = new Set(["committed", "failed", "cancelled", "activated", "activation_rejected", "override", "dismissed", "stored"]);
