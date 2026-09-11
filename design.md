# VaidyaAI — "Instrument" design spec

Implementation spec for the approved dashboard direction (option **2c**), including dark mode.
Target codebase: `frontend/` (React + Vite, plain CSS in `src/styles.css`, no framework).

Reference mockup: `VaidyaAI Dashboard Concepts.dc.html` — option `3a` (dark) and `2c` (light).

---

## 1. Principles this design encodes

These are not cosmetic. The existing components (`Dashboard.jsx`, `components/Absent.jsx`) already
distinguish *checked and clear* from *could not check*; the visual language must keep them distinct.

1. **An absence never looks like a value.** Anything not measured / not assessed is rendered with a
   **dashed outline and no fill**, in `--mono`, never in a risk colour. Never grey-out a real value
   into the same treatment.
2. **Risk colour is categorical, not decorative.** Only three: `--green` (in range), `--amber`
   (medium / borderline), `--rust` (high / above threshold). No other colour carries meaning.
3. **No blue anywhere.** Palette is warm: sand/clay in light, warm brown-black in dark.
4. **The chart is the explanation.** Every number is shown against the thing it was compared to
   (reference band, threshold arc, axis), because the platform's claim is that decisions are evidenced.
5. **Motion is entry-only.** Charts draw/grow once on mount, ~0.3–1.4s, then rest. Nothing loops
   except a single 2.4s `shimmer` on the "not measured" radar point. Respect
   `prefers-reduced-motion` (§7).

---

## 2. Design tokens

Define both themes as CSS custom properties on `:root`, with dark under
`[data-theme="dark"]`. Replace the current `:root` block in `src/styles.css`.

```css
:root {
  /* surfaces */
  --bg:         #efe9e0;
  --header:     #e6ded1;
  --header-line:#d8cdbc;
  --panel:      #fbf8f3;
  --panel-line: #ded3c2;
  --grid:       #e2d8c8;   /* chart gridlines / radar rings */
  --hairline:   #ebe2d3;   /* in-panel dividers */
  --track:      #e8dfd0;   /* chart baselines, gauge rest arc */
  --band:       #dfe6cf;   /* "usual range" band fill */
  --band-line:  #c9bca7;   /* dashed band for a value never measured */

  /* ink */
  --ink:        #2b2419;   /* headings, values, needle */
  --ink-2:      #4a3f30;   /* panel titles, emphasis in body copy */
  --body:       #5b4f3f;   /* body copy, chart axis labels */
  --muted:      #7d6f5d;   /* metadata, footnotes */
  --mono:       #8a7c69;   /* monospace micro-labels, absence text */

  /* semantic */
  --green:      #7d8f52;   /* in range — fills/markers */
  --green-text: #5f6f3c;   /* in range — text (contrast-safe) */
  --amber:      #c08a26;   /* medium / borderline */
  --rust:       #a44a2a;   /* high / above threshold */
  --brand:      #7b5836;   /* the italic "AI" in the wordmark */
  --radar-fill: rgba(164, 74, 42, .16);
}

[data-theme="dark"] {
  --bg:         #14100c;
  --header:     #1d1813;
  --header-line:#2e2620;
  --panel:      #1c1712;
  --panel-line: #2f2720;
  --grid:       #332a22;
  --hairline:   #2d251e;
  --track:      #2d251e;
  --band:       #333d24;
  --band-line:  #4d4334;

  --ink:        #f3ece0;
  --ink-2:      #dccfbc;
  --body:       #bcae9d;
  --muted:      #948674;
  --mono:       #948674;

  --green:      #9cb463;
  --green-text: #adc472;
  --amber:      #dba842;
  --rust:       #e0764c;
  --brand:      #dba842;
  --radar-fill: rgba(224, 118, 76, .20);
}
```

**Rules**

- Every colour in components comes from a token. No literal hex outside these two blocks.
- SVG uses the same tokens: `stroke="var(--rust)"`, `fill="var(--ink)"`.
- Markers that sit on a chart line get `border: 3px solid var(--panel)` so they read as separate
  from the track in both themes.
- Dark is **not** an inversion: semantic hues are lifted in lightness/chroma (`#a44a2a` → `#e0764c`)
  so the three risk colours stay distinguishable on a dark ground.

### Theme switching

No in-app toggle in this design. Set the theme once, on `<html>`:

```js
// src/lib/theme.js
export function applyTheme() {
  const stored = localStorage.getItem('vaidyaai-theme');           // 'light' | 'dark' | null
  const system = matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  document.documentElement.dataset.theme = stored || system;
}
```

Call `applyTheme()` in `src/main.jsx` before render. If a toggle is added later it only writes
`localStorage` and re-sets `data-theme` — no component knows about the theme.

---

## 3. Typography

| Role | Family | Size / weight |
|---|---|---|
| Wordmark, big verdict words (gauge label "High") | **Instrument Serif** 400 | 24px wordmark, 30px gauge label |
| UI, body copy, panel titles | **IBM Plex Sans** 400 / 500 | 13–14px body, 14px/500 panel titles |
| Micro-labels, values, metadata, axis labels | **IBM Plex Mono** 400 / 500 | 11–13px, `letter-spacing: .10–.12em` on uppercase labels |

Load with one `<link>`:
`Instrument+Serif:ital@0;1` · `IBM+Plex+Sans:wght@400;500;600` · `IBM+Plex+Mono:wght@400;500`.

Conventions:
- **All numeric values are monospace** (`IBM Plex Mono`, 500) — they align down the column.
- Uppercase mono micro-labels for metadata and axes (`SEP 12 · 67 RESULTS · 4 ASSESSED`, `LOW MEDIUM HIGH`).
- Never below 11px. Body copy 13–13.5px, line-height 1.55.
- Serif is reserved for the wordmark and the single verdict word. Do not use it for body copy.

---

## 4. Layout

Page shell, 1060px reference width, fluid below it:

```
header (48px content, 18px/30px padding, --header bg, 1px --header-line bottom)
  wordmark                                    metadata (mono, right)
main (padding: 26px 30px)
  grid 1fr 1fr, gap 16px
    [ panel: Overall risk (gauge) ]  [ panel: Coverage of the five topics (radar) ]
  grid 1fr, gap 16px
    [ panel: Where each result sits against its reference range (range chart) ]
```

- **Panel**: `background: var(--panel); border: 1px solid var(--panel-line); border-radius: 14px;
  padding: 22px 24px;`
- Two-column grid collapses to one column below 900px; the range chart's
  `190px 1fr 96px` row grid collapses to `1fr auto` with the bar spanning both columns below 560px.
- No shadows anywhere. Separation comes from the border and the panel/bg contrast.

Route mapping (existing pages keep their routes):

| Route | Panels |
|---|---|
| `/reports/:id` | gauge, radar, range chart, then the existing flagged-condition cards / "In short" section restyled with these tokens |
| `/timeline` | same panel + token system; trend chart uses the range-chart's line/threshold vocabulary |
| `/reports/:id/doctor-summary` | tokens + typography only, no charts (it is a passage) |

---

## 5. The three charts

All three are hand-authored SVG with a fixed `viewBox` and `width="…" height="…"`; no chart library.
Values below are the mockup's geometry — keep it and drive only the data-dependent numbers from props.

### 5.1 Risk gauge — "Overall risk"

`<svg width="290" height="216" viewBox="0 0 290 216">`

- Rest arc: `M25 152 A120 120 0 0 1 265 152`, `stroke: var(--track)`, `stroke-width: 18`, round caps.
- Three band arcs on top of it, drawn in sequence:
  - low: `M25 152 A120 120 0 0 1 105 40` — `var(--green)`, `stroke-dasharray: 200`
  - medium: `M112 37 A120 120 0 0 1 182 38` — `var(--amber)`, `stroke-dasharray: 90`
  - high: `M188 42 A120 120 0 0 1 265 152` — `var(--rust)`, `stroke-dasharray: 200`
- Needle: `<line x1="145" y1="152" x2="145" y2="56">` `stroke: var(--ink)`, width 3.5, round cap,
  inside a `<g>` with `transform-origin: 145px 152px`.
- Hub: `<circle cx="145" cy="152" r="8" fill="var(--ink)">`.
- Verdict label: `<text x="145" y="188" text-anchor="middle">` Instrument Serif 30px, `var(--ink)`.
  **It must sit below the hub** — inside the arc it collides with the needle.
- Scale row under the SVG: flex `space-between`, mono 11px `var(--mono)`, `margin-top: 8px`.

Needle angle from risk level (degrees, `rotate(deg)` about the hub):
`low → -60`, `medium → -10`, `high → 38`, and **no needle at all** when nothing could be assessed —
render the rest arc plus the absence line (§6) instead of parking the needle at "low".

Caption under the panel (verbatim intent): *"The needle reflects the highest risk level any single
topic reached — it is not an average."*

### 5.2 Radar — "Coverage of the five topics"

`<svg width="278" height="212" viewBox="0 0 278 212">`

- Three concentric pentagons + five spokes, `stroke: var(--grid)`, `fill: none`, width 1.
  Outer `139,22 250,102 207,192 71,192 28,102`; mid `139,56 205,104 179,158 99,158 73,104`;
  inner `139,90 161,106 152,124 126,124 117,106`; spokes from centre `139,106`.
- Data polygon: `fill: var(--radar-fill)`, `stroke: var(--rust)`, width 2.5, fades in.
- Assessed vertices: `r="4"` filled `var(--rust)`, popped in with `cellIn`, staggered 80ms.
- **A topic with no assessment is a dashed, unfilled circle** — `r="4.5"`, `fill: none`,
  `stroke: var(--mono)`, `stroke-dasharray: 2 2`, looping `shimmer` — and its axis label uses
  `var(--mono)` instead of `var(--body)`. The polygon must pass through the centre on that axis.
- Axis labels: mono 10.5px, `var(--body)`; the unassessed one `var(--mono)`.

Caption: *"Kidney sits at zero because nothing was measured — a dotted point, not a low score."*

### 5.3 Range chart — "Where each result sits against its reference range"

One row per measurement, grid `190px 1fr 96px`, gap 16px, rows gapped 14px:

1. **name** — 13.5px `var(--ink)`
2. **track** — `position: relative; height: 22px` containing, absolutely positioned:
   - baseline: `top: 9px; left/right: 0; height: 3px; background: var(--track); border-radius: 99px`
   - usual-range band: `top: 6px; height: 9px; background: var(--band); border-radius: 99px`,
     `left`/`width` in % from the reference interval
   - excess bar (only when a threshold was crossed): `top: 9px; height: 3px; background: var(--rust)`,
     from the band edge to the marker, animated with `barGrow`
   - marker: 15px circle, `background: var(--rust)` / `var(--green)`,
     `border: 3px solid var(--panel)`, popped in with `cellIn`
3. **value** — mono 500 13px, right-aligned, `var(--rust)` when flagged / `var(--green-text)` when in range

Header row: panel title left, `SHADED BAND = USUAL RANGE` (mono 11px `var(--mono)`) right.

Footnote under the rows, above a `1px var(--hairline)` divider: the lab-flagged-but-unassessed count.

---

## 6. Absence states (must be implemented exactly)

| State (from the payload) | Rendering |
|---|---|
| Measured, in range | solid `var(--green)` marker on its band; value in `var(--green-text)` |
| Measured, threshold crossed | `var(--rust)` marker + rust excess bar; value in `var(--rust)` |
| **Not on the report** | row at `opacity: .75`; band drawn as `1px dashed var(--band-line)` with **no fill**; no marker; value column `—` in `var(--mono)`; name followed by mono 11px `NOT ON REPORT` |
| **Rejected reading** (`state: 'rejected'`) | same dashed treatment, label `NOT USABLE`, plus the payload's rejection reason as a mono 11px line under the name |
| **Topic not assessed** | radar: dashed unfilled vertex + `var(--mono)` axis label; gauge: no needle; card: `NOT CHECKED` in mono `var(--mono)`, dashed 1px `var(--band-line)` panel border instead of solid |
| **Lab-flagged, not assessed here** | never plotted on any chart; listed in the footnote with the lab's own value in `var(--amber)` |

`NOT CHECKED` / `NOT ON REPORT` are **never** rendered in `--green`.

---

## 7. Motion

One `@keyframes` block; entry animations only, all `both`-filled so they hold their end state.

```css
@keyframes rise     { from { opacity:0; transform:translateY(16px) } to { opacity:1; transform:none } }
@keyframes glide    { from { opacity:0; transform:translateX(-10px) } to { opacity:1; transform:none } }
@keyframes fadeIn   { from { opacity:0 } to { opacity:1 } }
@keyframes barGrow  { from { transform:scaleX(0) } to { transform:scaleX(1) } }          /* transform-origin:left */
@keyframes drawLine { from { stroke-dashoffset:var(--len,400) } to { stroke-dashoffset:0 } }
@keyframes cellIn   { from { opacity:0; transform:scale(.6) } to { opacity:1; transform:scale(1) } }
@keyframes sweep    { from { transform:rotate(-96deg) } to { transform:rotate(38deg) } } /* end = risk angle */
@keyframes shimmer  { 0%,100% { opacity:.25 } 50% { opacity:.7 } }
```

Timing, in order:

| Element | Animation |
|---|---|
| Panels | `rise .5s both`, stagger `0 / .08s / .16s` |
| Gauge band arcs | `drawLine` `.9s .3s`, `.7s .6s`, `.9s .8s` ease-out; each arc's `--len` = its `stroke-dasharray` |
| Gauge needle | `sweep 1.5s .5s cubic-bezier(.3,1.4,.4,1)` — slight overshoot, like an instrument settling; `to` rotation = the risk angle |
| Radar polygon | `fadeIn .9s .55s` |
| Radar vertices | `cellIn .4s`, from `.8s`, +80ms each |
| Range rows | `glide .5s`, from `.3s`, +80ms each |
| Excess bars | `barGrow .8s cubic-bezier(.2,.8,.2,1)`, from `.45s`, +100ms each |
| Range markers | `cellIn .45s cubic-bezier(.3,1.5,.4,1)`, from `1.05s`, +100ms each — markers land last |
| Unassessed radar point | `shimmer 2.4s 1.1s ease-in-out infinite` (the only loop) |

`drawLine` requires the element to carry both `stroke-dasharray` (the path length) and
`--len` (the same number).

Reduced motion — required:

```css
@media (prefers-reduced-motion: reduce) {
  * { animation: none !important; transition: none !important; }
  /* end states must be static-correct: dashoffset 0, scale 1, needle at its risk angle */
}
```

So the needle's rotation must also be applied as a static `transform` on the `<g>`, with `sweep`
animating *to* that same angle — not left to the keyframe alone.

---

## 8. Accessibility

- Text contrast ≥ 4.5:1 in both themes; the token pairs above satisfy it (`--green-text` exists
  because `--green` does not pass as text).
- Colour is never the only signal: every risk colour is paired with a word (`High`, `In range`,
  `NOT CHECKED`) and every absence with a dashed outline.
- Charts: `role="img"` + `<title>` on each SVG stating the finding in words
  ("Overall risk: high, driven by the diabetes finding"). Give the range chart's rows a parallel
  visually-hidden table, or keep the existing `<table>` markup and hide the bars from AT.
- Focus rings: `outline: 2px solid var(--rust); outline-offset: 2px` — do not remove.

---

## 9. Build order

1. Replace the `:root` block in `src/styles.css` with the two token blocks (§2); add `applyTheme()`
   to `src/main.jsx`.
2. Retire literal colours across `styles.css` in favour of tokens; add typography (§3) and the
   `@keyframes` block (§7).
3. Restyle the shell — `.nav` → header (§4), `.card` → panel, `.disclaimer` → mono footnote.
4. Build the three charts as `components/RiskGauge.jsx`, `components/CoverageRadar.jsx`,
   `components/RangeChart.jsx`, each taking already-derived data — no thresholds or clinical logic
   in the chart components.
5. Wire them into `pages/Dashboard.jsx` above the existing flagged-condition cards. Feed them from
   the data the page already computes (`verdicts` from `valueVerdicts`, `dashboard.conditions`,
   `dashboard.overall.risk`) so nothing on screen is counted twice.
6. Apply §6 absence states through the existing `Absent` / `Value` / `Risk` primitives — the charts
   should receive an explicit "not available" state, never `null` coerced to a number.
7. Add `prefers-reduced-motion` and the SVG `<title>`s (§7–8).
