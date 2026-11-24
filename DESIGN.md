---
name: Jira Reporting Assistant
description: Side panel and floating chat that answer Foresight and Jira questions with the evidence beside every figure.
colors:
  accent: "#3b5bdb"
  accent-hover: "#2f4bc0"
  page: "#fafafa"
  surface: "#ffffff"
  ink: "#0a0a0a"
  ink-2: "#3d3d3d"
  muted: "#6b6b6b"
  line: "#e8e8e8"
  line-strong: "#d4d4d4"
  danger: "#b42318"
  danger-bg: "#fef3f2"
  warn: "#9a4a00"
typography:
  title:
    fontFamily: "Segoe UI, system-ui, -apple-system, Roboto, Arial, sans-serif"
    fontSize: "16px"
    fontWeight: 600
    lineHeight: 1.3
  claim:
    fontFamily: "Segoe UI, system-ui, -apple-system, Roboto, Arial, sans-serif"
    fontSize: "14px"
    fontWeight: 600
    lineHeight: 1.4
  body:
    fontFamily: "Segoe UI, system-ui, -apple-system, Roboto, Arial, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "Segoe UI, system-ui, -apple-system, Roboto, Arial, sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.5
    fontFeature: "tnum"
  caption:
    fontFamily: "Segoe UI, system-ui, -apple-system, Roboto, Arial, sans-serif"
    fontSize: "12px"
    fontWeight: 400
    lineHeight: 1.5
rounded:
  sm: "8px"
  md: "12px"
  pill: "22px"
spacing:
  xs: "8px"
  sm: "12px"
  md: "16px"
  lg: "20px"
  xl: "24px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.surface}"
    rounded: "{rounded.sm}"
    padding: "0 16px"
    height: "36px"
  button-primary-hover:
    backgroundColor: "{colors.accent-hover}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "0 16px"
    height: "36px"
  button-secondary-hover:
    backgroundColor: "{colors.page}"
  chat-launcher:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.surface}"
    rounded: "{rounded.pill}"
    padding: "0 18px 0 14px"
    height: "44px"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "8px 12px"
  proof-frame:
    backgroundColor: "{colors.page}"
    textColor: "{colors.ink-2}"
    typography: "{typography.label}"
    rounded: "{rounded.sm}"
  proof-row:
    padding: "8px 12px"
  error-notice:
    backgroundColor: "{colors.danger-bg}"
    textColor: "{colors.danger}"
    rounded: "{rounded.sm}"
    padding: "8px 12px"
  chat-panel:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.md}"
    width: "380px"
    height: "580px"
---

# Design System: Jira Reporting Assistant

## Overview

**Creative North Star: "Monochrome Proof"**

A quiet, near-colourless working tool whose one recurring gesture is evidence. Every summary, answer and warning list is a short claim in semibold followed directly by a hairline-framed block of rows: label on the left, figure on the right. The frame is the system's signature; everything else steps back so it reads first.

Density is moderate and calm: one system sans at regular and semibold, sentence case throughout, tabular numerals in every figure. Surfaces are white on a faint grey page, separated by 1px rules rather than shadows. Colour is spent sparingly: a single blue for the one primary action and focus, red only for states that are genuinely wrong (over-allocated, overdue, errors), amber only for "check this" notices.

The same world runs on two surfaces: the extension side panel (Tailwind v4 theme tokens) and the floating chat, which lives in a shadow root on the host page and re-declares the same values as custom properties.

**Key Characteristics:**
- Claim, then proof frame, for every answer, summary and warning list.
- Neutral greyscale from #fafafa to #0a0a0a; one blue accent; red and amber reserved for state.
- Hairline rules (1px #e8e8e8) do the structural work; shadow only where the chat floats over a foreign page.
- One system sans, two working weights, sentence case, tabular numerals.
- Gently rounded rectangles (8px) for every control and frame.

## Colors

A fine neutral scale carrying almost all of the interface, with one blue voice and two state colours.

### Primary
- **Proof Blue** (accent): the single primary button in a section, the chat Send button, focus outlines, text caret, the demo/AI mode dot when a model is live, and link hover. Never decorative.
- **Proof Blue Deep** (accent-hover): hover state of the primary button only.

### Neutral
- **Ink** (ink): headings, claims, figures in proof rows, the chat launcher fill.
- **Graphite** (ink-2): body copy under a claim, proof-row labels, links at rest.
- **Ash** (muted): section headings, hints, captions, sources line, the user's own question in the chat, placeholders.
- **Hairline** (line): proof-row dividers, section dividers, panel and frame borders.
- **Hairline Strong** (line-strong): input and secondary-button borders, link underline at rest, scrollbar thumb.
- **Page** (page): the proof frame fill, side panel page, hover fill for quiet buttons.
- **Surface** (surface): working surfaces (side panel main, chat panel, inputs).

### State
- **Alert Red** (danger) on **Alert Wash** (danger-bg): over-allocated / overdue figures (semibold red text in a proof row) and error notices.
- **Caution Amber** (warn): "things to check" counts and partial-read notices. Text only, no fill.

### Named Rules
**The One Blue Rule.** Blue marks the one action that moves the user forward and the element that has focus. A section never has two blue buttons; once data exists, "Read again" drops to secondary.

**The State-Only Colour Rule.** Red and amber appear only when a figure or message is actually wrong or incomplete, and always alongside words that say so ("over-allocated", "Stopped at the page limit"). Colour is never the only signal.

## Typography

**Body Font:** Segoe UI (with system-ui, -apple-system, Roboto, Arial, sans-serif)

**Character:** A workhorse system sans used at small sizes and two working weights; the hierarchy comes from weight and grey value, not size jumps. There is no display role.

### Hierarchy
- **Title** (600, 16px side panel / 15px chat, 1.3): product name in the side panel header; "Ask about this project" in the chat header.
- **Claim** (600, 14px, 1.4): the one-line statement above a proof frame ("2 people over-allocated next week:"), and status lines while reading.
- **Body** (400, 14px, 1.5): explanatory sentences, intro copy, chat paragraphs. Field labels use 500.
- **Label** (400, 13px, tabular numerals): proof-row labels and figures. Section headings in the side panel use this size at 600 in muted grey, sentence case.
- **Caption** (400, 12px): hints under fields, the sources line, mode/date line in the chat header, proof-row detail lines, footer notice.

### Named Rules
**The Tabular Figures Rule.** Every number in a proof row uses tabular numerals and is right-aligned, so columns of figures scan vertically.

**The Sentence Case Rule.** Headings, buttons and labels are sentence case. No uppercase labels, no tracking.

## Layout

Single column at both sizes. The side panel stacks sections (Source, Data, Ask) separated by 1px hairline rules, each with 20px padding and 12px between its children; the header and footer share the 20px inset. The chat is a fixed 380 x 580px panel (shrinking to the viewport minus 32px / 48px), 24px from the bottom-right corner (16px under 480px viewport width), with an 18px-padded scrolling log whose answers sit 20px apart and a 12px compose bar.

Spacing steps observed: 8, 12, 16, 20, 24px; tighter 2-7px gaps live only inside rows and lists.

Inside a proof row, label and figure sit on one baseline with at least 12px between them; the figure takes the right edge and the label wraps.

## Elevation & Depth

Flat by default. Depth is conveyed by the page/surface value step (#fafafa against #ffffff) and hairline borders. The only shadow belongs to the chat, because it floats over a page the extension does not control.

### Shadow Vocabulary
- **Float** (`box-shadow: 0 16px 40px rgba(10,10,10,0.10), 0 2px 6px rgba(10,10,10,0.06)`): chat panel and chat launcher only.
- **Focus halo** (`box-shadow: 0 0 0 3px rgba(59,91,219,0.15)` with an accent border): focused text inputs.

### Named Rules
**The Hairline Over Shadow Rule.** Inside a surface, structure is drawn with 1px rules. Shadow is reserved for something floating over someone else's page.

## Shapes

Gently rounded rectangles (8px) for buttons, inputs, proof frames, suggestion chips and notices; a softer 12px for the chat panel as a whole; a full pill (22px) for the floating launcher only. Status dots are 6px circles. Icons are drawn inline SVG at 1.6px stroke with round caps.

## Components

### Buttons
Restrained and flat; weight and fill carry the hierarchy.
- **Shape:** gently rounded (8px).
- **Primary:** accent fill, white semibold text, 36px high (40px in the chat compose bar), 16px side padding. Hover deepens to accent-hover. Disabled at 45% opacity.
- **Secondary:** white fill, 1px line-strong border, ink text at 500, same size. Hover fills with page grey.
- **Text link:** graphite text with a line-strong underline offset 2px; hover turns text and underline blue.
- **Focus:** 2px accent outline, 2px offset, on everything.

### Proof Frame (signature)
The claim's evidence. A list on page grey with a 1px hairline border, 8px corners, and hairline dividers between rows. Each row: label left in graphite, figure right in ink with tabular numerals; a label-only row renders in ink. An alert figure turns semibold red. In the chat a row may carry a muted 12px detail line below, and a label that matches exactly one source becomes a link to it. Remaining sources follow the frame in a 12px "Sources:" line.

### Inputs / Fields
- **Style:** white fill, 1px line-strong border, 8px corners, 14px text, muted placeholder, blue caret.
- **Focus:** border turns accent with a 3px 15% accent halo; no outline.
- **Field:** 500-weight label above, 12px muted hint below.

### Section (side panel)
Hairline-topped block with a 13px semibold muted heading and 20px padding. Disclosure rows ("More options", "things to check") use a drawn 12px chevron that rotates 90 degrees when open.

### Chat Launcher and Panel
Ink-filled pill with chat icon and "Ask" in white semibold; hover lightens slightly, press nudges down 1px. The panel rises in over 220ms (8px and 98% scale) on an ease-out curve, disabled under reduced motion. Its header shows the title, a 6px mode dot (grey for demo mode, blue when a model is live) with a text label, and a quiet 32px close button.

### Notices
Errors: red text on alert wash, 8px corners, 8-12px padding. Warnings: amber text only.

## Do's and Don'ts

### Do:
- **Do** follow every claim with its proof frame: hairline border, page-grey fill, label left, figure right.
- **Do** keep one blue element per section: the forward action or the focused control.
- **Do** pair every red or amber value with words that name the problem.
- **Do** use tabular numerals and right alignment for every figure.
- **Do** separate surfaces with 1px #e8e8e8 rules and the page/surface value step.

### Don't:
- **Don't** use chat bubbles; the user's question is plain right-aligned muted text and the answer is claim plus proof.
- **Don't** use blue for decoration, icons or headings.
- **Don't** add shadows inside a surface; shadow belongs only to the floating chat.
- **Don't** use uppercase labels, eyebrows or tracked small caps above headings.
- **Don't** introduce a numbered-stepper flow; the side panel is sections, not steps.
