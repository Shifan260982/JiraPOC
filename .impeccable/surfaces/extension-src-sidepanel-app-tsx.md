---
version: 1
slug: "extension-src-sidepanel-app-tsx"
primary_target: "extension/src/sidepanel/App.tsx"
related_targets: ["extension/src/overlay/App.tsx"]
---

# Extension side panel and floating chat

Mode: Operate. Two surfaces, one world: the extension side panel (connect, read, open chat) and the floating chat on Foresight tool pages.

Audience and job: Scrum Masters read the Foresight tool and prepare updates; stakeholders ask questions in the chat. Both must understand the panel at a glance ("hard to understand" was the complaint about v1). Demo audience: client stakeholders, synthetic data only.

Constraints: chat appears on the tool's origin only; demo mode (no LLM) must be labelled; every answer shows its sources; WCAG 2.2 AA.

## Direction contract

THESIS: Every claim is immediately followed by the evidence that proves it. Refuses the bubble-chat assistant and the numbered-stepper wizard.

OWN-WORLD: A fine neutral scale from #FAFAFA to #0A0A0A, white working surfaces with hairline #E8E8E8 rules, one blue accent #3B5BDB used only for the primary action and focus, red and amber only for over-allocated, overdue and warning states. Workhorse system sans at two weights, sentence case, tabular numerals.

STORY: The visitor sees what is connected, what was read and when, and can ask a question within one glance; answers state the claim in one line, then show the rows behind it with links to source.

FIRST VIEWPORT: Side panel: product name and source line at top; a "Source" section (tool address, change link); a "Data" section whose claim line reads like "14 workstreams and 39 issues read" with framed proof rows below and one primary button "Read again"; an "Ask" section with "Open chat on this page". Chat: a 380px panel bottom-right on the tool page, header with mode label, claim + framed proof rows per answer, input with Send.

FORM: Monochrome Proof (challenger), position 1 of the dealt hand; seed:c627267354a0f7f1. Signature move: claim-and-proof pairing, the proof frame (hairline-bordered rows on #FAFAFA, label left, figure right) used for every answer, summary and warning list.

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
