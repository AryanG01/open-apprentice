# Open Apprentice: design system

The visual contract for `apps/web`. Written in the awesome-design-md section format so an agent can read it before it touches a
style. References studied: Details.so (calm light surface, near-black ink, pill controls, one variable typeface, content as the hero),
and the Linear and Raycast DESIGN.md files (surface ladders and hairlines instead of shadows). We borrow the discipline, not the
dark theme: this is a tool people open in daylight to look at banners, so the page stays out of the way of the picture.

## 1. Visual theme and atmosphere

A quiet, warm-neutral workbench. The banner is the loudest thing on every screen; the interface is paper, ink and one green.
Mode: **Operate** for the editor, result and question; **Persuade** for the first screen only. Dials: variance 5, motion 4, density 4.
Light by default, a full dark mode under `prefers-color-scheme: dark`. No gradients, no glow, no decorative dots, no emoji, no
eyebrow labels, no card grids of identical tiles.

## 2. Colour palette and roles

One neutral family (warm grey), one accent (NVIDIA green, used for verified state and the logo mark, never for text on white).

| Token | Light | Dark | Role |
|---|---|---|---|
| `--bg` | `#fdfdfc` | `#0f0f0e` | page |
| `--surface` | `#f4f4f2` | `#181817` | cards, panels |
| `--surface-2` | `#ebebe8` | `#222221` | selected tab, pressed, chips |
| `--raised` | `#ffffff` | `#1d1d1c` | inputs sitting on a surface |
| `--ink` | `#111110` | `#f3f3f1` | text, primary button |
| `--ink-2` | `#64625f` | `#a3a19d` | secondary text (5.9:1 on `--bg`) |
| `--ink-3` | `#8f8d89` | `#7a7875` | placeholders only |
| `--line` | `rgb(17 17 16 / 0.09)` | `rgb(255 255 255 / 0.09)` | hairlines |
| `--line-strong` | `rgb(17 17 16 / 0.2)` | `rgb(255 255 255 / 0.2)` | input borders |
| `--accent` | `#76b900` | `#8fd11a` | verified mark, selected box, logo |
| `--ok` / `--ok-soft` | `#2f5d00` / `#e6f3d1` | `#a6d95a` / `#1d2a10` | pass pills |
| `--bad` / `--bad-soft` | `#b3261e` / `#fbe7e4` | `#ff8a80` / `#351916` | errors |
| `--warn` / `--warn-soft` | `#8a5a00` / `#fcefd2` | `#f2c15a` / `#33290f` | questions, caveats |

Rules: pure black and pure white never appear as page colours. Secondary text on a coloured surface is tinted from that surface.
Annotation colours on the user's banner (yellow box, green selected box) are chosen to read on any image, not from the palette.

## 3. Typography

Geist Variable for everything, Geist Mono Variable for numbers, model names and file facts. Weights 450 to 620 (never only 400 and 700).

| Role | Size / line | Weight | Tracking |
|---|---|---|---|
| display (first screen) | `clamp(2.4rem, 5.4vw, 3.9rem)` / 1.02 | 560 | -0.04em |
| h2 (step title) | `1.75rem` / 1.15 | 560 | -0.025em |
| h3 | `1rem` / 1.3 | 600 | -0.01em |
| body | `0.9375rem` / 1.55 | 450 | -0.005em |
| lede | `1.125rem` / 1.5, max 52ch | 450 | -0.01em |
| label | `0.78rem` / 1.3 | 520 | 0 |
| mono | `0.78rem` / 1.4 | 450 | 0 |

Body measure 65ch, `text-wrap: balance` on headings, `pretty` on paragraphs, `tabular-nums` on every number.

## 4. Component styling

Shape lock: controls 10px, cards 16px, stages 14px, buttons and chips fully round. Nothing else.

- **Primary button:** `--ink` fill, `--bg` text, 40px, pill, 560 weight. Hover: 82% ink. `:active`: `scale(.97)`.
- **Secondary:** `--raised` fill, 1px `--line-strong`. **Quiet:** transparent, no border.
- **Inputs:** 36px, `--raised`, 1px `--line-strong`, 10px radius; focus: ink border plus a 3px ink ring at 12% alpha.
- **Cards:** one elevation declaration only, a fill on `--surface`. No border and shadow together.
- **Pills:** pass (`--ok-soft`), caveat (`--warn-soft`), neutral (`--surface-2`). No pills over images.
- **Tabs:** text links, the selected one on a `--surface-2` pill.
- **Focus:** 2px ink ring with 2px offset on every interactive element, never the browser default.

## 5. Layout principles

Content column 1120px; 32px gutters (16px under 760px). First screen is a two-column split (copy and the drop target left, a real
before/after render right); steps 2 and 3 are workbenches: the banner and its boxes on the left (sticky), the part list on the right.
Spacing scale 4, 8, 12, 16, 24, 32, 48, 80. More space above a heading than below it.

## 6. Depth and elevation

Surface ladder (`--bg` to `--surface` to `--surface-2`) and hairlines. One soft tinted shadow exists, for the story-card image on the
first screen only: `0 1px 2px rgb(30 28 20 / .05), 0 18px 40px -16px rgb(30 28 20 / .22)`.

## 7. Motion

One authored moment per screen change: panels rise 6px and fade over 260ms with `cubic-bezier(.23, 1, .32, 1)`, children staggered 40ms.
Press feedback 140ms. Hover colour changes 160ms, only under `(hover: hover)`. Only `transform` and `opacity` animate. Keyboard actions
(arrow keys moving a box) never animate. `prefers-reduced-motion` removes movement and keeps opacity.

## 8. Do and do not

Do: show the real banner and real renders; name model jobs in plain words; keep every control labelled; theme selection, scrollbar and
caret from the palette. Do not: add icons that decorate, put text on the accent green, use a modal for anything that can sit inline,
use em dashes in copy, repeat the same layout family twice on a screen.

## 9. Agent prompt guide

"Use `DESIGN.md`. Tokens live in `:root` in `apps/web/src/styles.css`. Keep every class and aria-label that `tests/e2e/*.mjs` and
`video/capture/adapt.mjs` select on. Verify with `node /tmp/.../shoot.mjs` at 1440x900 and 390x844 before and after."
