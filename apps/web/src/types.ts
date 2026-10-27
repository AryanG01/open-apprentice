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
  variant: "control" | "audit" | "hybrid";
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

export interface OogArm {
  variant: "search" | "model" | "hybrid";
  arm: string;
  trials: number;
  committed: number;
  correct: number;
  wrong: number;
  abstained: number;
  errors: number;
  tokens: number;
}

export interface Evidence {
  oog?: OogArm[];
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

export interface CandidatePool {
  from_model: number;
  from_search: number;
  model_error: string | null;
}

export interface WitnessSearch {
  status: string;
  elapsed_ms: number;
  cases: number;
  solver_version: string;
}

export interface Reasoning {
  candidate_count: number;
  rejected_count: number;
  selection: {
    source: string;
    split: number[];
    entropy_bits: number;
    cost_units: number;
    score: number;
    scenes_considered: number;
    witness_searches: WitnessSearch[];
  } | null;
  settle: WitnessSearch | null;
  solver: { calls: number; max_calls: number; elapsed_s: number };
}

export interface LiveState {
  id: string;
  mode: string;
  replay: boolean;
  pool: CandidatePool | null;
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
  reasoning?: Reasoning;
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
  repaired_by: "model" | "fixture" | "none";
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
  model: { available: boolean; can_start: boolean; id: string; spend_usd: number; cap_usd: number; error: string | null };
  replay: { available: boolean; recorded_at: string | null; id: string };
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

export interface SvgRow {
  id: string;
  tag: string;
  editable: boolean;
  reason?: string;
  world?: { x: number; y: number; width: number; height: number };
}

export interface SvgPair {
  card: string;
  badge: string;
}

export interface SvgSample {
  id: string;
  bytes: number;
  coverage: { editable: number; listed: number };
  suggested_pairs: SvgPair[];
}

export interface SvgInspect {
  source: string;
  inventory: { hash: string; elements: SvgRow[]; inert_vector_elements: number; coverage: { editable: number; listed: number } };
  suggested_pairs: SvgPair[];
}

export interface SvgApply {
  passed: boolean;
  hash_before: string;
  hash_after: string;
  diff: { element: string; attribute: string; old: string | null; new: string }[];
  unrelated_byte_changes: number;
  scope: string;
  rows: { badge: string; card: string; expected: { x: number; y: number; width: number; height: number }; measured: { x: number; y: number } | null; max_error_px: number | null; passed: boolean }[];
  moved_elements: string[];
  only_selected_badges_moved: boolean;
  concept_hash: string;
  original_svg: string;
  modified_svg: string;
  patch: unknown;
}

export interface SvgHarm {
  all_rejected: boolean;
  attempts: { attempt: string; rejected: boolean; reasons: string[] }[];
}

// ---- Campaign lane (/api/campaign) ----
export interface CampaignFixture {
  id: string;
  locale: string;
  kind: "teaching" | "banner" | "broken" | "untagged";
  png: string;
}

export interface CampaignCandidate {
  origin: string;
  reproduces: boolean;
  reason: string;
}

export interface RuleRow {
  role: string;
  position: string;
  size: string;
  z: number | null;
  style: string[];
}

export interface ReadingOption {
  id: "fixed" | "relative";
  label: string;
  status: string;
  png: string | null;
  product_box: number[];
  verification: CampaignVerification | null;
}

export interface ReadingQuestion {
  kind: "reading";
  text: string;
  probe_png: string;
  options: ReadingOption[];
}

export interface CampaignWorkspace {
  workspace_id: string;
  learned: { origin: string; reading: string | null; question: ReadingQuestion | null; rule_table: RuleRow[]; candidates: CampaignCandidate[] };
  teaching: { before_png: string; after_png: string };
}

export interface CampaignCheck {
  name: string;
  passed: boolean;
  detail: string;
}

export interface CampaignVerification {
  passed: boolean;
  failed: string[];
  checks: CampaignCheck[];
}

export interface CampaignViolation {
  kind: string;
  node_id: string;
  detail: unknown;
}

export interface CampaignPreview {
  outcome: string;
  origin: string;
  fits: boolean;
  violations: CampaignViolation[];
  png: string;
}

export type CampaignEngine = "konva" | "fabric";

export interface CampaignRun {
  run_id: string;
  fixture_id: string;
  backend: CampaignEngine;
  locale: string;
  status: "ready" | "question" | "applied" | "unchanged" | "needs_roles" | "unsupported_format" | "failed" | "blocked";
  problems: string[];
  provenance: Record<string, string | number | object>;
  result: { png: string; verification: CampaignVerification | null } | null;
  previews: CampaignPreview[];
  preference: { outcome: string; version: number } | null;
  preference_seen: number | null; // saved-preference version when the question was asked; sent back with the answer
  explanation?: { text: string; origin: string; problems: string[] };
}

export interface CampaignRoleLayer {
  id: string; // the real layer id, as in the mapping
  label: string; // the opaque id the model saw (L1..Ln)
  type: string;
  box: (number | null)[];
  text?: string;
  fontSize?: number;
  asset?: string;
  children?: string[];
}

export interface CampaignRoles {
  mapping: Record<string, string>;
  origin: "model" | "heuristic";
  problems: string[];
  candidates: CampaignRoleLayer[];
  model: "on" | "off";
}

export interface CampaignProcedure {
  backend: CampaignEngine;
  origin: "model" | "reference";
  accepted: boolean;
  attempts: { passed: boolean; cases: { fixture: string; outcome: string; passed: boolean; failed_checks: string[] }[]; note?: string }[];
  notes: string[];
  cached?: boolean;
  model: "on" | "off";
}

export interface CampaignScope {
  scope: string;
  locale: string;
  active: { outcome: string; version: number } | null;
  history: { version: number; outcome: string; parent: number | null }[];
}

/** One layer of a banner as the editor holds it: a pixel box [x, y, w, h] on the 1280 x 720 image. */
export interface AdaptLayer {
  role: string;
  box: number[];
  text: string;
  font_px: number;
  bold: boolean;
  color: string;
  fill: string;
}

export interface AdaptUpload {
  upload_id: string;
  origin: "model" | "manual";
  language: string;
  layers: AdaptLayer[];
  problems: string[];
  note: string;
  model: string;
}

export interface AdaptBanner {
  banner_id: string;
  locale: string;
  png: string;
}

/** The owner's product page as Tavily read it, with facts that were each found on the page (api/pages.py). */
export interface PageFact {
  text: string;
  quote: string;
}
export interface PagePrice extends PageFact {
  amount: string;
  currency: string;
}
export interface PageInfo {
  page_id: string;
  url: string;
  title: string;
  chars: number;
  origin: "tavily" | "mock";
  language: string;
  facts: { product_name: PageFact | null; prices: PagePrice[]; features: PageFact[]; legal: PageFact[] };
  copy: { origin: "model" | "template"; options: { id: string; headline: string }[]; price: string | null; cta: string; legal: string; problems: string[] };
  problems: string[];
  note: string;
}
export interface PageCheck {
  status: "match" | "mismatch" | "unknown";
  rows: { field: string; banner: string[]; page: string[]; ok: boolean; detail: string }[];
  notes: string[];
}
