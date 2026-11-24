# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users
- **Scrum Masters** set the assistant up, read data from the client's Foresight board, and prepare stakeholder updates and reports that they used to build by hand in Excel.
- **Stakeholders and managers** ask questions themselves ("who is over-allocated next week?", "what is outstanding for November?") through the chat, without knowing how the data was gathered.

Both groups are equally important (confirmed 2026-11-23). Stakeholders are not technical; Scrum Masters know Jira well.

## Product Purpose
Remove manual Jira/Foresight reporting. The assistant reads project and resourcing data from the client's Foresight tool (or Jira directly), answers natural-language questions with evidence, and produces stakeholder reports. Success: a stakeholder gets a correct, sourced answer in one question, and a Scrum Master produces a report without touching Excel.

## Positioning
Answers are computed from the client's own data by deterministic functions and cite their source (issue keys, workstreams, weeks); the language model only explains. It never invents progress, dates or allocations.

## Operating Context
- Runs as a Chrome/Edge extension: a side panel for connecting and reading data, and a floating chat on Foresight tool pages only (confirmed).
- Foresight board: a static HTML export with workstreams grouped by programme; per workstream a month/week grid of outstanding bugs/stories by delivery point, milestones, weekly role allocations (permanent / contract / unknown, red when over-allocated) and % focus.
- Jira CSV exports with standard and custom fields (Delivery Point, Developer, Lead Developer, Technical Analyst, Tester, blocking and test links, worklogs).
- Demos to client stakeholders use synthetic sample data only (Doe surnames, invented keys and IDs), never real client data.

## Capabilities and Constraints
- Backend: Python + FastAPI (decided). Extension: Manifest V3, React + TypeScript + Tailwind.
- LLM provider: **undecided**. The chat must work in a no-LLM demo mode that answers from deterministic tools, and switch to a provider by configuration.
- No user authentication yet; backend runs locally.
- Terminology: workstream, delivery point, W/C (week commencing), allocation, over-allocated, outstanding, milestone, % focus.

## Evidence on Hand
- Synthetic samples: `samples/` (generated; safe to show).
- Real client exports exist locally but must never be copied into the repo, demos or screenshots.
- No customer quotes, metrics or case studies exist; none may be invented.

## Product Principles
1. Every number has a source the user can open.
2. Say what is missing rather than reporting zero.
3. Plain language first; Jira jargon only where the user already uses it.
4. Least access: only the tool's site and the backend.
5. Client data stays with the client; demos use synthetic data.

## Accessibility & Inclusion
WCAG 2.2 AA for the side panel and chat: keyboard operable, visible focus, screen-reader announcements for scan progress and chat replies, colour never the only signal (over-allocation also labelled).
