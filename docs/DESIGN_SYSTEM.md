# Design System — PharmaGPT

**Version:** 1.0  
**Date:** 2026-06-27  
**Source file:** `pharmagpt/static/css/style.css` (~3,309 lines)

---

## 1. Design Philosophy

PharmaGPT uses a **dark, professional theme** appropriate for technical/enterprise pharmaceutical software. The design prioritises:

- **Information density** — validation engineers work with large amounts of structured data
- **Clarity over decoration** — no gratuitous animations or distracting UI chrome
- **Regulatory feel** — navy/blue palette evokes trust, precision, and compliance
- **Keyboard-friendly** — inputs, buttons, and modals all accessible without a mouse

There is no external CSS framework. All styles are hand-crafted in a single `style.css` file.

---

## 2. Colour Palette

### 2.1 Background Layers

| Token (conceptual) | Hex | Usage |
|--------------------|-----|-------|
| `bg-deepest` | `#0a0e1a` | Root page background |
| `bg-sidebar` | `#0d1117` | Left sidebar panel |
| `bg-surface` | `#161b27` | Cards, input fields, panels |
| `bg-elevated` | `#1e2535` | Hover states, selected rows, modals |
| `bg-border` | `#2d3748` | Dividers, input borders |

### 2.2 Primary Brand (Navy/Blue)

| Token | Hex | Usage |
|-------|-----|-------|
| `brand-primary` | `#1e40af` | Primary buttons, active states |
| `brand-primary-hover` | `#1d4ed8` | Button hover |
| `brand-accent` | `#3b82f6` | Links, focus rings, highlights |
| `brand-light` | `#60a5fa` | Secondary text accents, icons |
| `brand-sidebar-active` | `#1e3a5f` | Active sidebar item background |

### 2.3 Text

| Token | Hex | Usage |
|-------|-----|-------|
| `text-primary` | `#e2e8f0` | Body text, headings |
| `text-secondary` | `#94a3b8` | Subtitles, labels, timestamps |
| `text-muted` | `#64748b` | Placeholder text, disabled states |
| `text-inverse` | `#ffffff` | Text on coloured buttons |

### 2.4 Semantic Colours

| Token | Hex | Usage |
|-------|-----|-------|
| `success` | `#10b981` | Extraction OK badges, success toasts |
| `warning` | `#f59e0b` | Overdue date highlights, caution states |
| `danger` | `#ef4444` | Delete buttons, error states, overdue badges |
| `info` | `#3b82f6` | Info badges, KB folder counts |

### 2.5 Validation Document Type Colours

Each of the 11 validation document types has a dedicated accent colour defined in `validation_config.js` and reflected in CSS:

| Doc Type | Colour |
|----------|--------|
| URS | `#6366f1` (indigo) |
| DQ | `#8b5cf6` (violet) |
| FAT | `#ec4899` (pink) |
| SAT | `#f97316` (orange) |
| IQ | `#10b981` (emerald) |
| OQ | `#14b8a6` (teal) |
| PQ | `#3b82f6` (blue) |
| FMEA | `#ef4444` (red) |
| CAPA | `#f59e0b` (amber) |
| Deviation | `#6b7280` (grey) |
| Change Control | `#84cc16` (lime) |

---

## 3. Typography

| Role | Family | Weight | Size |
|------|--------|--------|------|
| Body | System UI stack (`-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif`) | 400 | 14px |
| Headings (H1) | Same stack | 700 | 20px |
| Headings (H2) | Same stack | 600 | 17px |
| Headings (H3) | Same stack | 600 | 15px |
| Code / pre | `'Courier New', monospace` | 400 | 13px |
| Sidebar labels | Same stack | 500 | 12px |
| Timestamps | Same stack | 400 | 11px |

Line height: `1.6` for body text, `1.3` for headings.  
No external web fonts are loaded — fully offline-capable.

---

## 4. Layout

### 4.1 Page Structure

```
┌─────────────────────────────────────────────────────┐
│  HEADER  (60px, fixed top)                          │
├────────────┬────────────────────────────────────────┤
│            │                                        │
│  SIDEBAR   │  MAIN CONTENT AREA                    │
│  (260px,   │  (flex-1, scrollable)                 │
│  fixed)    │                                        │
│            │                                        │
└────────────┴────────────────────────────────────────┘
```

- **Header:** `height: 60px; position: fixed; z-index: 100`
- **Sidebar:** `width: 260px; position: fixed; top: 60px; height: calc(100vh - 60px); overflow-y: auto`
- **Main:** `margin-left: 260px; margin-top: 60px; padding: 24px; overflow-y: auto`

### 4.2 Sidebar Sections

1. Navigation icons (Home, Chat, Documents, Insights, Knowledge Base)
2. Validation document type buttons (collapsible)
3. Projects list (scrollable)
4. Regulatory tags footer
5. Specialization tags footer

### 4.3 Content Views

All views are rendered inside the main content area. JavaScript toggles `display` to switch between:
- `.dashboard-view`
- `.chat-view`
- `.documents-view`
- `.insights-view`
- `.kb-view`
- `.validation-view`

---

## 5. Components

### 5.1 Buttons

```css
/* Primary */
.btn-primary {
  background: #1e40af;
  color: #fff;
  border-radius: 6px;
  padding: 8px 16px;
  font-weight: 500;
}
.btn-primary:hover { background: #1d4ed8; }

/* Danger */
.btn-danger {
  background: #ef4444;
  color: #fff;
}

/* Ghost */
.btn-ghost {
  background: transparent;
  border: 1px solid #2d3748;
  color: #94a3b8;
}
```

### 5.2 Cards / Panels

```css
.card {
  background: #161b27;
  border: 1px solid #2d3748;
  border-radius: 8px;
  padding: 16px;
}
```

### 5.3 Input Fields

```css
input, textarea, select {
  background: #0d1117;
  border: 1px solid #2d3748;
  border-radius: 6px;
  color: #e2e8f0;
  padding: 8px 12px;
}
input:focus {
  border-color: #3b82f6;
  outline: none;
  box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.25);
}
```

### 5.4 Chat Bubbles

```css
.message-row { display: flex; gap: 12px; padding: 12px 0; }

/* User message */
.bubble.user {
  background: #1e3a5f;
  border-left: 3px solid #3b82f6;
  border-radius: 8px;
  padding: 12px 16px;
}

/* AI message */
.bubble.model {
  background: #161b27;
  border-left: 3px solid #10b981;
  border-radius: 8px;
  padding: 12px 16px;
}
```

### 5.5 Source Strip

Appears below AI responses when document context was injected:

```css
.sources-strip {
  font-size: 11px;
  color: #64748b;
  border-top: 1px solid #2d3748;
  padding-top: 6px;
  margin-top: 8px;
}
.source-tag {
  background: #1e2535;
  border: 1px solid #2d3748;
  border-radius: 4px;
  padding: 2px 6px;
  margin: 2px;
  display: inline-block;
}
```

### 5.6 Document Viewer (A4 Style)

```css
.doc-viewer {
  background: #fff;
  color: #1a1a1a;
  max-width: 794px;       /* A4 width at 96dpi */
  min-height: 1123px;     /* A4 height at 96dpi */
  margin: 0 auto;
  padding: 60px 72px;
  box-shadow: 0 4px 24px rgba(0,0,0,0.4);
  font-family: 'Times New Roman', serif;
  line-height: 1.7;
}
```

This is the only component that uses **light background + dark text** — mimicking a printed Word document.

### 5.7 Wizard Steps

```css
.wizard-step {
  display: none;
}
.wizard-step.active {
  display: block;
}
.step-indicator {
  display: flex;
  gap: 8px;
  margin-bottom: 24px;
}
.step-dot {
  width: 28px; height: 28px;
  border-radius: 50%;
  background: #2d3748;
  display: flex; align-items: center; justify-content: center;
  font-size: 12px; font-weight: 600;
}
.step-dot.active { background: #1e40af; color: #fff; }
.step-dot.done { background: #10b981; color: #fff; }
```

### 5.8 Knowledge Base Table

```css
.kb-table { width: 100%; border-collapse: collapse; }
.kb-table th {
  background: #0d1117;
  color: #94a3b8;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  padding: 8px 12px;
  border-bottom: 1px solid #2d3748;
}
.kb-table tr:hover { background: #1e2535; cursor: pointer; }
.kb-table td { padding: 10px 12px; border-bottom: 1px solid #1e2535; }
```

### 5.9 Badges

```css
.badge {
  border-radius: 4px;
  padding: 2px 8px;
  font-size: 11px;
  font-weight: 500;
}
.badge-success { background: rgba(16,185,129,0.15); color: #10b981; }
.badge-warning { background: rgba(245,158,11,0.15); color: #f59e0b; }
.badge-danger  { background: rgba(239,68,68,0.15);  color: #ef4444; }
.badge-info    { background: rgba(59,130,246,0.15);  color: #60a5fa; }
```

---

## 6. Iconography

No icon library is imported. Icons are implemented as:
- Unicode emoji (🗂, 📋, ⚙️, 📄) in sidebar navigation labels
- CSS-drawn indicators (coloured dots, step circles)
- Validation doc type icons are emoji characters stored in `validation_config.js`

---

## 7. Motion & Animation

Animations are minimal by design:
- **SSE streaming cursor:** blinking `|` appended to in-progress AI text
- **Sidebar item transitions:** `transition: background 0.15s ease`
- **Button hover states:** `transition: background 0.1s ease`
- No page transitions or skeleton loaders

---

## 8. Print Styles (PDF Export)

Activated when the user clicks "Print / PDF" in the document viewer:

```css
@media print {
  .sidebar, .header, .toolbar { display: none; }
  .doc-viewer {
    box-shadow: none;
    margin: 0;
    padding: 40px 60px;
    page-break-inside: avoid;
  }
  h1, h2, h3 { page-break-after: avoid; }
  table { page-break-inside: avoid; }
}
```

---

## 9. Responsive Behaviour

The app is primarily designed for desktop (1280px+). At narrower widths:
- Sidebar can be collapsed (hamburger toggle planned for v0.8)
- Chat bubbles stack correctly on tablets
- Document viewer scales down with `max-width: 100%`

Mobile-native layout is not a current priority.

---

## 10. DOCX Export Styling (python-docx)

The `doc_exporter.py` service applies Word-document styling programmatically:

| Element | Style |
|---------|-------|
| Page size | A4 (21cm × 29.7cm) |
| Margins | 1.25" left, 1.0" right, 1.0" top/bottom |
| Heading 1 | Navy (`#003366`), 16pt, bold, space-before 12pt |
| Heading 2 | Navy (`#003366`), 13pt, bold, space-before 8pt |
| Heading 3 | Dark grey (`#333333`), 11pt, bold |
| Body text | Black, 11pt, Calibri, 1.15 line spacing |
| Tables | Header row: navy background, white text; alternating row shading |
| Header | Company name + document title, 9pt, right-aligned |
| Footer | "CONFIDENTIAL — For Internal Use Only" + page number |
