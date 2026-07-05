# Design System — PharmaGPT

**Version:** 2.0 — "Executive Office"
**Date:** 2026-07-05
**Source files:** `pharmagpt/static/css/style.css` (~3,750 lines), `workspace.css`, and per-suite
CSS (`risk.css`, `urs.css`, `qual.css`, `report.css`, `qms.css`) which reuse the same `:root`
tokens defined in `style.css`.

> **Supersedes v1.0** (the earlier navy/blue "dark, professional theme" described in prior
> revisions of this document). See [PROJECT_MEMORY/DECISIONS.md](../PROJECT_MEMORY/DECISIONS.md)
> DEC-018 for the full rationale. This was a **visual redesign only** — no backend, API, database,
> route, or business-logic change accompanied it.

---

## 1. Design Philosophy

PharmaGPT uses a **warm, "business-attire" premium enterprise theme** — soft white / warm ivory /
stone / sand / beige / taupe / walnut brown / charcoal / soft olive-sage — replacing the earlier
navy/blue enterprise-software palette. The design prioritises:

- **Executive-office feel** — the app should read like a premium office environment (comparable in
  spirit to Stripe Dashboard, Linear, Notion Enterprise, Arc Browser, modern SAP Fiora), not a
  traditional dark technical dashboard.
- **Information density retained** — validation engineers still work with large amounts of
  structured data; the palette changed, the layout density did not.
- **Warmth over coolness** — no blue/navy/slate/cyan/purple hues anywhere in the UI; every accent
  is warm (brown, olive-sage, amber, terracotta) except the deliberately-distinct Information
  semantic colour (a muted blue-grey, used only for informational badges/status, never for buttons
  or brand chrome).
- **Consistency** — one set of tokens (`:root` in `style.css`) is shared by the core app shell and
  every suite (Risk, URS, Qualification, Validation Report, QMS). No screen has its own competing
  palette.

There is no external CSS framework. All styles are hand-crafted, split by domain per
[ARCHITECTURE.md](../PROJECT_MEMORY/ARCHITECTURE.md) §3/§17 (DEC-012).

---

## 2. Colour Palette

### 2.1 Backgrounds

| Token (CSS var) | Hex | Usage |
|---|---|---|
| `--bg` | `#F8F6F2` | Primary background (main content area) |
| `--bg-secondary` | `#F2EEE8` | Secondary background (headers, tints, table zebra) |
| `--surface` | `#FFFFFF` | Cards, inputs, panels, modals |

### 2.2 Brand — Walnut Brown (primary interactive)

| Token | Hex | Usage |
|---|---|---|
| `--blue-light` | `#7B5B45` | Primary button / active state (default shade) |
| `--blue` | `#6A4D39` | Primary button hover (darker shade) |
| `--navy` | `#2B2B2B` | Heading / strong-emphasis text |
| `--accent` | `#8FA68E` | Muted Sage accent (focus rings, hover borders, decorative dots/spinners — **not** primary buttons) |

These historical variable names (`--navy`, `--blue`, `--blue-light`) are kept so every existing
`var()` consumer across all 7 CSS files repaints automatically; new code may keep using them or the
plain-English aliases below.

### 2.3 Sidebar

| Token | Hex | Usage |
|---|---|---|
| `--sidebar-bg` | `#3F3A36` | Warm Charcoal — sidebar background |
| `--sidebar-hover` | `#544C45` | Sidebar item hover |
| `--sidebar-active` | `#7B5B45` | Active sidebar item (Walnut Brown) + `border-left: 3px solid rgba(255,255,255,.75)` indicator |

### 2.4 Text

| Token | Hex | Usage |
|---|---|---|
| `--text` | `#2B2B2B` | Primary text |
| `--text-muted` | `#66635F` | Secondary text (subtitles, labels, timestamps) |
| `--text-disabled` | `#9A948C` | Muted text (placeholders, disabled states) |

### 2.5 Borders

| Token | Hex | Usage |
|---|---|---|
| `--border` | `#DDD6CC` | Standard borders, dividers between input/card edges |
| `--divider` | `#E7E1D6` | Subtle internal separators (table headers, card headers) |

### 2.6 Semantic / Status Colours

| Token | Hex | Usage |
|---|---|---|
| `--success` | `#5B8C5A` | Success badges, "done" states, extraction-OK |
| `--warning` | `#C79B3B` | Warning badges, overdue-soon highlights |
| `--error` | `#C65B57` | Danger — delete buttons, error states, critical badges |
| `--info` | `#5C8FB5` | Information — the one intentionally-blue token, muted blue-grey, used **only** for informational badges/status (e.g. "processing", "pending"), never for brand chrome or buttons |

### 2.7 Chart / Data-Visualisation Palette

No charting library is used anywhere in the app (confirmed — no `<canvas>`/Chart.js/D3 usage as of
this writing). The closest analogues — risk-severity matrices, progress bars, and status
dot/badge colours — use the same warm palette: Sage (`--accent` / `--success`), Amber (`--warning`),
Terracotta (`#B9713C`, deep-orange family), and muted Olive/Taupe (`#6E6B35`, `#8A6E5E`) for
category markers that previously used purple/teal. If a real chart library is introduced in the
future, reuse this same set rather than defaulting to library defaults (which are typically
saturated/neon).

### 2.8 Suite-Specific Severity Tokens

`risk.css` defines its own small `:root` block (reused conceptually by URS/Qual/Report severity
badges):

```css
:root {
  --risk-critical: #C65B57;   /* Danger */
  --risk-high:     #B9713C;   /* Terracotta */
  --risk-medium:   #C79B3B;   /* Warning */
  --risk-low:      #5B8C5A;   /* Success */
  --risk-bg:       #F3EEE5;
  --risk-surface:  #FFFFFF;
  --risk-border:   #E3DCD0;
  --risk-accent:   #7B5B45;   /* Walnut Brown */
}
```

---

## 3. Typography

| Role | Family | Weight | Size |
|---|---|---|---|
| Body | **Inter** (Google Fonts), fallback `'Segoe UI', system-ui, -apple-system, sans-serif` | 400–500 | 13px |
| Headings (H1) | Inter | 700 | 20px |
| Headings (H2) | Inter | 600 | 17px |
| Headings (H3) | Inter | 600 | 15px |
| Code / pre | `'Courier New', monospace` | 400 | 13px |
| Sidebar labels | Inter | 500 | 12px |
| Timestamps | Inter | 400 | 11px |

Line height: `1.5`–`1.6` for body text, `1.3` for headings. Inter is loaded via
`@import url('https://fonts.googleapis.com/css2?family=Inter:...')` at the top of `style.css` (an
established precedent — the app previously loaded IBM Plex Sans the same way; DEC-005's "fully
offline-capable" framing referred to the app having no build step, not to font loading, which has
used a Google Fonts `@import` since v0.2).

---

## 4. Layout

Unchanged from v1.0 — this was a colour/token/typography redesign only, not a layout redesign.

### 4.1 Page Structure

```
┌─────────────────────────────────────────────────────┐
│  HEADER  (56px, white, minimal)                     │
├────────────┬────────────────────────────────────────┤
│            │                                        │
│  SIDEBAR   │  MAIN CONTENT AREA                    │
│  (240px,   │  (flex-1, scrollable)                 │
│  charcoal) │                                        │
│            │                                        │
└────────────┴────────────────────────────────────────┘
```

### 4.2 Sidebar Sections

Unchanged structure (Main Menu, Projects, Documents, Quality Management, Regulatory Scope footer) —
see [ARCHITECTURE.md](../PROJECT_MEMORY/ARCHITECTURE.md) §5/§7 for the live-navigation vs.
backend-complete-but-unwired suites (Risk/URS/Qualification/Validation Report still lack a wired
sidebar entry point — a pre-existing gap, unrelated to and not fixed by this redesign).

### 4.3 Enterprise Workspace Shell

Unchanged (`workspace.css`/`workspace.js`, DEC-017) — repainted with the new palette
(`.ent-ws-header` now Warm Charcoal instead of navy, step dots now Walnut/Sage/Success instead of
blue).

---

## 5. Components

### 5.1 Buttons

```css
/* Primary */
.btn-primary {
  background: #7B5B45;   /* Walnut Brown */
  color: #fff;
  border-radius: 8px;
  padding: 8px 20px;
  font-weight: 500;
}
.btn-primary:hover { background: #6A4D39; }

/* Secondary */
.btn-secondary {
  background: #fff;
  border: 1px solid #DDD6CC;
  color: #2B2B2B;
}

/* Danger */
.btn-danger {
  background: #C65B57;
  color: #fff;
}
```

Every suite's primary CTA (`.btn-urs-primary`, `.btn-qual-primary`, `.btn-risk-primary`,
`style.css`'s `.btn-primary`) now resolves to the same Walnut Brown — `var(--accent)` (Muted Sage)
is reserved for focus rings, hover-highlight borders, decorative dots, and spinners, never for a
primary call-to-action, so every screen's main button reads identically.

### 5.2 Cards / Panels

```css
.dash-card, .dash-stat-card, .vw-project-card, .insights-stat-card {
  background: #FFFFFF;
  border: 1px solid #E7E1D6;   /* --divider, softer than a full border */
  border-radius: 14px;         /* --radius-lg */
  box-shadow: 0 1px 3px rgba(61,47,33,0.07), 0 1px 2px rgba(61,47,33,0.05);
}
```

Dashboard KPI cards keep a 3px coloured top accent (project/blue-grey/success/warning/danger/
walnut) for at-a-glance scanning, small icon, large value, small uppercase subtitle label — no
heavy borders, soft warm-tinted shadow instead.

### 5.3 Input Fields

```css
input, textarea, select {
  background: #FFFFFF;
  border: 1px solid #DDD6CC;
  border-radius: 8px;         /* var(--radius); dedicated var(--radius-input): 10px for larger fields */
  color: #2B2B2B;
  padding: 8px 12px;
}
input:focus {
  border-color: #7B5B45;
  outline: none;
  box-shadow: 0 0 0 3px rgba(123,91,69,0.10);   /* warm walnut focus ring */
}
```

### 5.4 Chat Bubbles

```css
.bubble.user {
  background: #7B5B45;   /* was navy/blue */
  border-left: 3px solid #7B5B45;
  color: #fff;
}
.bubble.model {
  background: #FFFFFF;
  border-left: 3px solid #5B8C5A;   /* Success sage-green accent */
}
```

### 5.5 Tables

```css
th { background: #F2EEE8; color: #2B2B2B; text-transform: uppercase; font-size: 11px; }
tr:nth-child(even) td { background: #F2EEE8; }   /* soft zebra */
tr:hover td           { background: #EFE7D8; }   /* distinct hover highlight */
```

`th:first-child`/`th:last-child` pick up the shared `--radius` for a rounded header row. The one
deliberate exception remains the DOCX-mimicking `.val-doc-content` viewer table, which keeps a
solid Warm-Charcoal header row (`#3F3A36`) with white text to read as a formal printed document —
see §5.7.

### 5.6 Badges

```css
.badge-success { background: #EFF5EE; color: #5B8C5A; }
.badge-warning { background: #F5EFE1; color: #C79B3B; }
.badge-danger  { background: #F3E2DF; color: #C65B57; }
.badge-info    { background: #F3EEE5; color: #5C8FB5; }
```

Every one-off badge/tint colour formerly hardcoded per suite (risk severities, QMS status pills,
KB extraction badges, validation review scores, etc.) was swept to this same warm-tint family so no
two suites render the same semantic status in a different shade.

### 5.7 Document Viewer (A4 Style)

Unchanged — light background + dark text, the deliberate exception mimicking a printed Word
document (see [ARCHITECTURE.md](../PROJECT_MEMORY/ARCHITECTURE.md)). Its table header now uses
Warm Charcoal (`#3F3A36`) instead of the old navy, and its zebra striping uses the same warm tint
as every other table.

### 5.8 Modals

```css
.modal-overlay { background: rgba(63,58,54,0.55); }   /* warm-tinted overlay, was black */
.modal { border-radius: 4px; box-shadow: 0 4px 24px rgba(61,47,33,0.18); }
```

---

## 6. Iconography

Unchanged — Unicode emoji, no icon library, CSS-drawn indicators (coloured dots, step circles,
sidebar left-indicator bar).

---

## 7. Motion & Animation

Unchanged from v1.0.

---

## 8. Print Styles (PDF Export)

Unchanged from v1.0.

---

## 9. Responsive Behaviour

Unchanged — desktop-first (1280px+); the sidebar hides below a ~768px breakpoint (pre-existing,
not part of this redesign).

---

## 10. DOCX Export Styling (python-docx)

Unchanged — `doc_exporter.py` was **not** touched by this redesign (out of scope per the
UI-only mandate). Its navy (`#003366`) heading colour and header-row styling remain as documented
in the prior revision of this file; consider aligning it to Walnut Brown (`#7B5B45`)/Warm Charcoal
(`#3F3A36`) in a future pass if visual parity between the on-screen viewer and the exported .docx
is desired — see §11 Future Recommendations.

---

## 11. Migration Notes / Future Recommendations

- **Font loading**: Inter now loads via the same Google Fonts `@import` mechanism the app has used
  since v0.2 (previously IBM Plex Sans). No new offline-capability regression was introduced.
- **`docx_generator.py` / `doc_exporter.py`** still emit the old navy DOCX styling (out of scope for
  this UI-only redesign — see [CLAUDE.md](../PROJECT_MEMORY/CLAUDE.md) "Never modify business
  logic"). Recommended follow-up: repaint the exported-document heading/table colours to Walnut
  Brown / Warm Charcoal for full on-screen/exported-document visual parity.
- **Risk/URS/Qualification/Validation Report sidebar navigation** remains unwired (pre-existing gap,
  see [ARCHITECTURE.md](../PROJECT_MEMORY/ARCHITECTURE.md) §5) — their CSS was fully repainted and
  spot-verified by temporarily forcing their views visible in a browser, but they still have no
  live sidebar entry point. Wiring that navigation is a separate, previously-tracked item, not part
  of this redesign.
- **No chart library exists** in the codebase today (§2.7) — if one is introduced, reuse the warm
  palette defined here rather than a library's default (often neon) colours.
