import montage from "../public/montage/index.json";
import marks from "../public/marks.json";
import { AbsoluteFill, Audio, Freeze, Img, OffthreadVideo, Sequence, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { FPS, timeline, type Beat, type Box } from "./timeline";

const C = { navy: "#0c1c33", table: "#0f2440", ink: "#e8eef7", ink2: "#9fb3cf", cyan: "#7fd3ff", green: "#9be15d", amber: "#ffc35c", pink: "#ff5fa2" };
const FONT = "Barlow, 'Helvetica Neue', Arial, sans-serif";

/** Ducks the music under every line of narration. */
function musicVolume(frame: number, beats: Beat[]): number {
  const t = frame / FPS;
  const speaking = beats.some((b) => t >= b.start + 0.1 && t <= b.start + 0.3 + b.voSec + 0.2);
  return speaking ? 0.07 : 0.22;
}

export const Demo = () => {
  const { beats, total } = timeline();
  return (
    <AbsoluteFill style={{ background: C.navy, fontFamily: FONT }}>
      <style>{`@font-face{font-family:Barlow;font-weight:400;src:url(${staticFile("fonts/barlow-400.woff2")}) format("woff2")}@font-face{font-family:Barlow;font-weight:600;src:url(${staticFile("fonts/barlow-600.woff2")}) format("woff2")}`}</style>
      {beats.map((b) => (
        <Sequence key={b.id} from={Math.round(b.start * FPS)} durationInFrames={Math.round(b.dur * FPS)} name={b.id}>
          <Scene b={b} />
        </Sequence>
      ))}
      {beats.map((b) => (
        <Sequence key={`vo-${b.id}`} from={Math.round((b.start + 0.3) * FPS)} name={`vo-${b.id}`}>
          <Audio src={staticFile(`vo/${b.id}.wav`)} />
        </Sequence>
      ))}
      <Audio src={staticFile("music.wav")} volume={(f) => musicVolume(f, beats) * Math.min(1, (total * FPS - f) / (2 * FPS))} />
    </AbsoluteFill>
  );
};

function Scene({ b }: { b: Beat }) {
  return (
    <AbsoluteFill>
      {b.card === "title" ? <TitleCard /> : b.card === "results" ? <ResultsCard /> : b.card === "montage" ? <Montage /> : b.card === "arch" ? <Architecture dur={b.dur} /> : b.card === "breadth" ? <Breadth dur={b.dur} /> : b.clip ? <Clip b={b} /> : null}
      {b.onScreen ? <Headline text={b.onScreen} /> : null}
      {b.live ? <Tags b={b} /> : null}
      {b.explain ? <Explainer steps={b.explain} dur={b.dur} /> : null}
      <Captions b={b} />
    </AbsoluteFill>
  );
}

/** A stretch of the real capture: sped up if it is longer than its narration, last frame held if shorter; gently zoomed on its focus. */
function Clip({ b }: { b: Beat }) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const clip = b.clip!;
  const playFrames = Math.round(((clip.to - clip.from) / clip.rate) * fps);
  const z = zoom(b.focus, frame, fps);
  const video = (from: number, rate: number) => (
    <OffthreadVideo src={staticFile("capture.mp4")} startFrom={Math.round(from * fps)} playbackRate={rate} muted
      style={{ width: 1920, height: 1080, transform: z.transform, transformOrigin: z.origin }} />
  );
  return (
    <AbsoluteFill style={{ background: C.table }}>
      <Sequence durationInFrames={playFrames}>{video(clip.from, clip.rate)}</Sequence>
      {clip.held > 0 ? (
        <Sequence from={playFrames}>
          <Freeze frame={0}>{video(Math.max(0, clip.to - 0.1), 1)}</Freeze>
        </Sequence>
      ) : null}
    </AbsoluteFill>
  );
}

function zoom(box: Box, frame: number, fps: number) {
  // scale only as far as keeps the whole focus box in view, centre it, never reveal an edge of the frame
  if (!box) return { transform: "none", origin: "0 0" };
  const target = Math.max(1, Math.min(1.35, (1920 * 0.92) / box.width, (1080 * 0.82) / box.height));
  const s = 1 + (target - 1) * spring({ frame, fps, config: { damping: 200 }, durationInFrames: 40 });
  const cx = box.x + box.width / 2, cy = box.y + box.height / 2;
  const tx = Math.min(0, Math.max(1920 - 1920 * s, 960 - cx * s));
  const ty = Math.min(0, Math.max(1080 - 1080 * s, 540 - cy * s));
  return { transform: `translate(${tx}px, ${ty}px) scale(${s})`, origin: "0 0" };
}

function Headline({ text }: { text: string }) {
  const frame = useCurrentFrame();
  const o = interpolate(frame, [0, 12], [0, 1], { extrapolateRight: "clamp" });
  return (
    <div style={{ position: "absolute", top: 36, left: 48, opacity: o, transform: `translateY(${(1 - o) * -10}px)`,
      background: "rgba(8,20,38,.86)", border: `1px solid ${C.cyan}55`, color: "#fff", padding: "12px 20px", borderRadius: 10,
      fontSize: 38, fontWeight: 600, letterSpacing: 0.2 }}>
      {text}
    </div>
  );
}

function Tags({ b }: { b: Beat }) {
  return (
    <div style={{ position: "absolute", top: 40, right: 48, display: "flex", gap: 12, fontSize: 26, fontWeight: 600 }}>
      {b.live ? <span style={{ background: C.green, color: "#0b1d05", padding: "8px 14px", borderRadius: 8 }}>● Live run</span> : null}

    </div>
  );
}

/** What the system is doing while the screen works: steps that light up in order across the beat. */
function Explainer({ steps, dur }: { steps: string[]; dur: number }) {
  const frame = useCurrentFrame();
  const t = frame / FPS;
  const each = Math.max(0.8, (dur - 1) / steps.length);
  return (
    <div style={{ position: "absolute", left: 48, bottom: 170, display: "flex", gap: 10, alignItems: "center" }}>
      {steps.map((s, i) => {
        const on = interpolate(t, [0.4 + i * each, 0.8 + i * each], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
        return (
          <div key={s} style={{ display: "flex", alignItems: "center", gap: 10, opacity: 0.25 + 0.75 * on }}>
            <span style={{ background: `rgba(8,20,38,${0.7 + 0.2 * on})`, border: `2px solid ${on > 0.5 ? C.green : "#2a4670"}`, color: "#fff",
              padding: "10px 16px", borderRadius: 10, fontSize: 28, fontWeight: 600, transform: `translateY(${(1 - on) * 6}px)` }}>{s}</span>
            {i < steps.length - 1 ? <span style={{ color: C.cyan, fontSize: 30 }}>→</span> : null}
          </div>
        );
      })}
    </div>
  );
}

/** Karaoke captions from Kokoro's word timings: one short phrase at a time, the spoken word highlighted. */
function Captions({ b }: { b: Beat }) {
  const frame = useCurrentFrame();
  const ms = (frame / FPS - 0.3) * 1000;
  if (!b.words.length || ms < 0 || ms > b.voSec * 1000 + 300) return null;
  const groups: (typeof b.words)[] = [];
  for (const w of b.words) {
    const g = groups[groups.length - 1];
    if (!g || g.length >= 9 || /[.,;:!?]$/.test(g[g.length - 1].text)) groups.push([w]);
    else g.push(w);
  }
  const g = groups.find((x) => ms <= x[x.length - 1].endMs + 250) ?? groups[groups.length - 1];
  return (
    <div style={{ position: "absolute", bottom: 64, width: "100%", display: "flex", justifyContent: "center" }}>
      <div style={{ background: "rgba(4,10,20,.82)", padding: "12px 26px", borderRadius: 12, fontSize: 44, fontWeight: 600, color: "#cfd9e6", maxWidth: 1500, textAlign: "center" }}>
        {g.map((w, i) => (
          <span key={i} style={{ color: ms >= w.startMs && ms <= w.endMs + 120 ? "#fff" : undefined, textShadow: ms >= w.startMs && ms <= w.endMs + 120 ? `0 0 18px ${C.cyan}` : undefined }}>
            {w.text}{" "}
          </span>
        ))}
      </div>
    </div>
  );
}

const grid = { backgroundColor: C.table, backgroundImage: "linear-gradient(rgba(127,211,255,.07) 1px, transparent 1px), linear-gradient(90deg, rgba(127,211,255,.07) 1px, transparent 1px)", backgroundSize: "48px 48px" };

function TitleCard() {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const s = spring({ frame, fps, config: { damping: 120 } });
  return (
    <AbsoluteFill style={{ ...grid, alignItems: "center", justifyContent: "center", color: C.ink }}>
      <div style={{ transform: `scale(${0.92 + 0.08 * s})`, opacity: s, textAlign: "center" }}>
        <svg viewBox="0 0 32 32" width={150} height={150} style={{ fill: "none", stroke: C.cyan, strokeWidth: 1.6 }}>
          <rect x="3" y="5" width="15" height="10" rx="2" fill="rgba(127,211,255,.15)" />
          <rect x="14" y="19" width="15" height="9" rx="2" stroke={C.green} fill="rgba(155,225,93,.15)" />
          <path d="M6 18h8M17 31h9" />
        </svg>
        <div style={{ fontSize: 120, fontWeight: 600, color: "#fff", marginTop: 10 }}>Open Apprentice</div>
        <div style={{ fontSize: 46, color: C.ink2, marginTop: 6 }}>Show it once. It asks when unsure. It proves every edit.</div>
        <div style={{ fontSize: 34, color: C.green, marginTop: 40 }}>NVIDIA Nemotron · Nebius Token Factory</div>
      </div>
    </AbsoluteFill>
  );
}

function ResultsCard() {
  const rows: [string, string, string][] = [
    ["Refuses when the examples conflict", "12/12", "6/12"],
    ["Asks when the examples are ambiguous", "2/12", "0/12"],
    ["Learns the rule (frozen battery)", "22/48", "28/48"],
    ["Cost per run", "$0.17", "$0.26"],
  ];
  return (
    <AbsoluteFill style={{ ...grid, padding: "90px 140px", color: C.ink }}>
      <div style={{ fontSize: 64, fontWeight: 600, color: "#fff" }}>Measured, not claimed</div>
      <div style={{ fontSize: 30, color: C.ink2, marginTop: 8 }}>
        Frozen benchmark: 36 held-out episodes × 3 runs, live Nemotron, an independent scorer. Apprentice vs the same model acting freely.
      </div>
      <table style={{ marginTop: 40, fontSize: 40, borderCollapse: "collapse", width: "100%" }}>
        <thead>
          <tr style={{ color: C.ink2, fontSize: 30, textAlign: "left" }}>
            <th style={{ padding: 10 }} />
            <th>Apprentice</th>
            <th>Free agent</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([q, a, b]) => (
            <tr key={q} style={{ borderTop: "1px solid #2a4670" }}>
              <td style={{ padding: "16px 10px" }}>{q}</td>
              <td style={{ color: C.green, fontWeight: 600 }}>{a}</td>
              <td>{b}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div style={{ fontSize: 30, color: C.amber, marginTop: 30 }}>
        On plain learning the free agent scores higher. We publish that too, with every failure.
      </div>
      <div style={{ fontSize: 22, color: C.ink2, marginTop: 18 }}>Every screen in this video is a real session; waiting time is shortened in the edit.</div>
    </AbsoluteFill>
  );
}

type MTile = { i: number; name: string };

/** Real before/after renders from the run: a wave sweeps across the wall, turning each untidy diagram into its published one. */
function Montage() {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const tiles = (montage as MTile[]).slice(0, 32);
  const cols = 8;
  const real = Number(((marks as { marks: { name: string }[] }).marks.find((m) => m.name.startsWith("published-"))?.name ?? "published-0").split("-")[1]);
  const published = Math.round(interpolate(frame, [fps * 1.2, fps * 6.5], [0, real], { extrapolateLeft: "clamp", extrapolateRight: "clamp" }));
  return (
    <AbsoluteFill style={{ ...grid, padding: "120px 60px 60px" }}>
      <div style={{ position: "absolute", top: 36, left: 60, color: "#fff", fontSize: 48, fontWeight: 600 }}>
        Fix one diagram. It fixes the other hundred.
      </div>
      <div style={{ position: "absolute", top: 46, right: 60, color: C.green, fontSize: 40, fontWeight: 600, fontVariantNumeric: "tabular-nums" }}>
        {published} / 100 published
      </div>
      <div style={{ display: "grid", gridTemplateColumns: `repeat(${cols}, 1fr)`, gap: 14 }}>
        {tiles.map((t, k) => {
          const r = Math.floor(k / cols), c = k % cols;
          const p = interpolate(frame, [fps * (1.2 + (r + c) * 0.42), fps * (1.7 + (r + c) * 0.42)], [0, 100], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
          return (
            <div key={t.i} style={{ position: "relative", background: "#fff", borderRadius: 6, overflow: "hidden", aspectRatio: "16 / 10",
              boxShadow: p >= 100 ? `0 0 0 3px ${C.green}` : "0 0 0 1px #2a4670" }}>
              <Img src={staticFile(`montage/${t.i}-after.png`)} style={{ position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "contain" }} />
              <Img src={staticFile(`montage/${t.i}-before.png`)} style={{ position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "contain", clipPath: `inset(0 0 0 ${p}%)` }} />
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
}

const ARCH: [string, string][] = [
  ["Your .drawio files", "parsed, never executed"],
  ["Real draw.io engine", "locked headless Chromium, offline"],
  ["NVIDIA Nemotron", "on Nebius Token Factory, proposes rules"],
  ["Sandboxed interpreter", "exact arithmetic, no eval"],
  ["Probe search", "draws the diagram that splits the rules"],
  ["Byte-exact patch", "three independent checks, then publish"],
];

/** The pipeline, lit step by step as the narration walks through it. */
function Architecture({ dur }: { dur: number }) {
  const frame = useCurrentFrame();
  const t = frame / FPS;
  const each = (dur - 2) / ARCH.length;
  return (
    <AbsoluteFill style={{ ...grid, padding: "120px 90px", color: C.ink }}>
      <div style={{ fontSize: 60, fontWeight: 600, color: "#fff" }}>Under the hood</div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: "56px 70px", marginTop: 60 }}>
        {ARCH.map(([h, sub], i) => {
          const on = interpolate(t, [0.6 + i * each, 1.1 + i * each], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
          return (
            <div key={h} style={{ position: "relative", border: `2px solid ${on > 0.5 ? (i === 2 ? C.green : C.cyan) : "#2a4670"}`, borderRadius: 14,
              padding: "26px 28px", background: `rgba(8,20,38,${0.55 + 0.35 * on})`, opacity: 0.3 + 0.7 * on, transform: `translateY(${(1 - on) * 12}px)` }}>
              <div style={{ fontSize: 22, color: C.ink2 }}>{i + 1}</div>
              <div style={{ fontSize: 40, fontWeight: 600, color: "#fff" }}>{h}</div>
              <div style={{ fontSize: 28, color: C.ink2, marginTop: 6 }}>{sub}</div>
              {i % 3 !== 2 ? <div style={{ position: "absolute", right: -52, top: "42%", color: C.cyan, fontSize: 40, opacity: on }}>→</div> : null}
            </div>
          );
        })}
      </div>
      <div style={{ fontSize: 28, color: C.ink2, marginTop: 56 }}>Google Cloud Run · Cloud Tasks · Cloud Storage · a durable spending cap on every live call</div>
    </AbsoluteFill>
  );
}

const KINDS: [string, string][] = [
  ["gpu-data-hall-floor-plan", "Data-hall floor plan"],
  ["ai-platform-org-chart", "Org chart"],
  ["model-release-roadmap", "Roadmap"],
  ["spine-leaf-network", "Network topology"],
];

/** Not just flowcharts: one real published file of each other kind, each wiping from the untidy original to the fixed one. */
function Breadth({ dur }: { dur: number }) {
  const frame = useCurrentFrame();
  const t = frame / FPS;
  const each = (dur - 1.5) / KINDS.length;
  const pick = KINDS.map(([kind, label]) => ({ label, tile: (montage as MTile[]).find((m) => m.name.includes(kind)) })).filter((x) => x.tile);
  return (
    <AbsoluteFill style={{ ...grid, padding: "110px 70px 150px" }}>
      <div style={{ position: "absolute", top: 34, left: 70, color: "#fff", fontSize: 50, fontWeight: 600 }}>Not just flowcharts. Same skill, every file.</div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 26, height: "100%" }}>
        {pick.map(({ label, tile }, i) => {
          const show = interpolate(t, [i * each * 0.6, i * each * 0.6 + 0.4], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
          const wipe = interpolate(t, [i * each * 0.6 + 0.8, i * each * 0.6 + 2.2], [0, 100], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
          return (
            <div key={label} style={{ position: "relative", background: "#fff", borderRadius: 10, overflow: "hidden", opacity: show,
              transform: `scale(${0.96 + 0.04 * show})`, boxShadow: wipe >= 100 ? `0 0 0 4px ${C.green}` : "0 0 0 1px #2a4670" }}>
              <Img src={staticFile(`montage/${tile!.i}-after.png`)} style={{ position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "contain" }} />
              <Img src={staticFile(`montage/${tile!.i}-before.png`)} style={{ position: "absolute", inset: 0, width: "100%", height: "100%", objectFit: "contain", clipPath: `inset(0 0 0 ${wipe}%)` }} />
              <div style={{ position: "absolute", left: 14, bottom: 12, background: "rgba(8,20,38,.88)", color: "#fff", fontSize: 30, fontWeight: 600, padding: "6px 14px", borderRadius: 8 }}>
                {label}{wipe >= 100 ? <span style={{ color: C.green }}>  ✓ published</span> : null}
              </div>
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
}
