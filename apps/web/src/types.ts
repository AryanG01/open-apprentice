export interface Box {
  id: string;
  x: number;
  y: number;
  w: number;
  h: number;
  role: string;
}

export interface CanvasView {
  label: string;
  canvas: { w: number; h: number };
  boxes: Box[];
  note: string;
}

export interface Axes {
  intent: string;
  symbolic: string;
  native: string;
  held_out: string;
}

export interface Check {
  name: string;
  passed: boolean;
  detail: string;
}

export interface OptionView {
  id: string;
  boxes: Box[];
  stands_for: string[];
}

export interface Attempt {
  candidate: number;
  source?: string;
  diagnosis: string;
  failed_stage: string | null;
  cases: { stage: string; passed: boolean; scene: string; native_actions: number }[];
}

export interface VersionRow {
  version: number;
  origin?: string;
  parent: number | null;
  program_hash: string;
  active: boolean;
}

export interface Mismatch {
  status: string;
  native_status: string;
  abstract_check_passed: boolean;
  semantic_model_trusted: boolean;
  diffs: { key: string; expected: number[]; observed: number[] }[];
}

export type Program = Record<string, unknown>[];

export interface Step {
  id: string;
  mode: "Learn" | "Reuse" | "Transfer" | "Challenge";
  title: string;
  summary: string;
  axes: Axes;
  canvases?: CanvasView[];
  base?: CanvasView;
  options?: OptionView[];
  extra_options?: string[];
  query?: { query_id: string; candidate_set_hash: string; source: string; groups: string[][]; entropy: number };
  rule_text?: string;
  sealed_hash?: string;
  ledger_entries?: number;
  ledger_chain_verified?: boolean;
  note?: string;
  binding?: { version: number; backend: string; program_hash: string; concept_hash: string; origin: string; scope: string; native_actions: number };
  program?: Program;
  checks?: Check[];
  verifier_passed?: boolean;
  same_concept_hash?: boolean;
  mismatch?: Mismatch;
  attempts?: Attempt[];
  old_program?: Program;
  new_program?: Program;
  versions?: VersionRow[];
  concept_hash_before?: string;
  concept_hash_after?: string;
  binding_concept_hash?: string;
  rule_unchanged?: boolean;
}

export interface Demo {
  label: string;
  origin: string;
  generated_at: string;
  sealed_hash: string;
  steps: Step[];
}

export interface MethodRow {
  scheduled: number;
  correct: number;
  committed_wrong: number;
  abstained: number;
  tokens: number;
  failures: Record<string, number>;
}

export interface RunEvidence {
  run: string;
  label: string;
  episodes: number;
  methods: Record<string, MethodRow>;
  origins: string[];
}

export interface TeachingTrials {
  concept: string;
  model: string;
  reasoning_effort: string;
  trials: number;
  recovered: number;
  ready_but_wrong: number;
  unresolved: number;
}

export interface ExperimentArm {
  name: string;
  arm: string;
  trials: number;
  errors: number;
  committed: number;
  correct: number;
  wrong: number;
  abstained: number;
  wrong_share_of_committed: number | null;
  tokens: number;
}

export interface Evidence {
  experiments?: ExperimentArm[];
  generated_at: string;
  runs: RunEvidence[];
  teaching_trials: TeachingTrials[];
  caveats: string[];
}

export interface LiveLabel {
  mode: string;
  candidate_rules: string;
  native_procedures: string;
  verifier: string;
}

export interface LiveQuestion {
  source: string;
  query_id: string;
  candidate_set_hash: string;
  base: CanvasView;
  options: { id: string; boxes: Box[] }[];
}

export interface LiveConcept {
  rule_text: string;
  sealed_hash: string;
  ledger_entries: number;
  ledger_chain_verified: boolean;
  answer_source: string;
}

export interface LiveState {
  id: string;
  mode: string;
  meter: Meter | null;
  fallbacks: string[];
  label: LiveLabel;
  state: string;
  intent_state: string;
  queries_asked: number;
  rounds: number;
  note: string;
  demonstration: { canvases: CanvasView[] };
  question?: LiveQuestion;
  correction?: { supported: boolean; message: string };
  concept?: LiveConcept;
}

export interface LiveRun {
  meter: Meter | null;
  fallbacks: string[];
  backend: string;
  tool_change: boolean;
  width: number;
  canvases: CanvasView[];
  native_passed: boolean;
  native_diffs: { key: string; expected: number[]; observed: number[] }[];
  native_error: string | null;
  verifier_passed: boolean;
  checks: Check[];
  binding: { version: number; origin: string; program_hash: string; concept_hash: string; native_actions_used: number | null };
  can_repair: boolean;
  concept_hash: string;
}

export interface LiveRepair {
  meter: Meter | null;
  fallbacks: string[];
  status: string;
  attempts: Attempt[];
  old_program: Program;
  new_program: Program | null;
  versions: VersionRow[];
  concept_hash_before: string;
  concept_hash_after: string;
  rule_unchanged: boolean;
}

export interface Meter {
  model: string;
  label: string;
  session_tokens: number;
  session_calls: number;
  session_usd: number;
  unknown_cost_calls: number;
  server_spend_usd: number;
  server_cap_usd: number;
  note: string;
}

export interface ReadyInfo {
  engine: boolean;
  engine_error: string | null;
  model: { available: boolean; id: string; spend_usd: number; cap_usd: number; error: string | null };
}

export interface BreakFailure {
  width: number;
  height: number;
  x: number;
  y: number;
  native_passed: boolean;
  failed_checks: string[];
  native_diffs: { key: string; expected: number[]; observed: number[] }[];
  native_error: string | null;
}

export interface BreakResult {
  backend: string;
  tool_change: boolean;
  binding: { version: number; origin: string; program_hash: string };
  tested: number;
  passed: number;
  failed: number;
  failures: BreakFailure[];
  seed: number;
  elapsed_s: number;
  coverage: string;
}

export interface ReplayCheck {
  name: string;
  passed: boolean | null;
  detail: string;
}

export interface ReplayResult {
  passed: boolean;
  checks: ReplayCheck[];
}
