// Turns script.json + the capture's marks + the measured voice lengths into a timeline. Pure: the same inputs give the same
// edit. A clip is never slowed down; when it is shorter than its narration, its last frame is held.
import script from "../script.json";
import marks from "../public/marks.json";
import captions from "../public/captions/index.json";

export const FPS = 30;
const PAD = 0.9; // seconds of air after each line
const MIN_CARD = 4;

export type Word = { text: string; startMs: number; endMs: number };
export type Box = { x: number; y: number; width: number; height: number } | null;

export type Beat = {
  id: string;
  text: string;
  start: number; // seconds into the video
  dur: number;
  voSec: number;
  words: Word[];
  card?: "title" | "results" | "montage" | "arch" | "breadth" | "finale";
  clip?: { from: number; to: number; rate: number; held: number };
  focus: Box;
  live: boolean;
  onScreen?: string;
  explain?: string[];
};

type ScriptBeat = { id: string; text: string; clip?: [string, string]; card?: "title" | "results" | "montage" | "arch" | "breadth" | "finale"; focus?: string; live?: boolean; onScreen?: string; explain?: string[] };
type Mark = { name: string; t: number; box: Box };

const markList = (marks as { marks: Mark[]; frameOffset: number }).marks;
const offset = (marks as { frameOffset: number }).frameOffset ?? 0;
const SCALE = (marks as { scale?: number }).scale ?? 1; // CSS pixels of the capture → video pixels
const at = (name: string): Mark => markList.find((x) => x.name === name) as Mark;
const has = (name: string) => markList.some((x) => x.name === name);

const scaleBox = (b: Box): Box => (b ? { x: b.x * SCALE, y: b.y * SCALE, width: b.width * SCALE, height: b.height * SCALE } : null);

export function timeline() {
  let start = 0;
  const beats: Beat[] = [];
  for (const b of (script as { beats: ScriptBeat[] }).beats) {
    if (b.clip && !(has(b.clip[0]) && has(b.clip[1]))) continue; // e.g. an offline dry run has no question to show
    const c = (captions as Record<string, { seconds: number; words: Word[] }>)[b.id] ?? { seconds: 0, words: [] };
    let dur = Math.max(c.seconds + PAD, b.card ? MIN_CARD : 2);
    let clip: Beat["clip"];
    if (b.clip) {
      const from = Math.max(0, at(b.clip[0]).t - offset);
      const to = Math.max(from + 0.5, at(b.clip[1]).t - offset);
      const len = to - from;
      const rate = Math.max(1, len / dur);
      clip = { from, to, rate, held: Math.max(0, dur - len / rate) };
    }
    if (b.card === "results") dur += 3;
    beats.push({
      id: b.id, text: b.text, start, dur, voSec: c.seconds, words: c.words, card: b.card, clip,
      focus: b.focus && has(b.focus) && at(b.focus).box ? scaleBox(at(b.focus).box) : null, live: !!b.live, onScreen: b.onScreen, explain: b.explain,
    });
    start += dur;
  }
  return { beats, total: start };
}
