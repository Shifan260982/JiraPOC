# AI-Powered Jira Reporting Assistant — Architecture (Phase 1)

Status: **Draft for review** · 2026-11-20
Scope: answers Section 9 of the project brief. No code has been written.

---

## 0. Assumptions and open decisions

These must be confirmed before Phase 2. Items marked **Blocking** change the design.

| # | Topic | Assumption used in this draft | Blocking? |
|---|---|---|---|
| D1 | Backend stack | **Decided 2026-11-20: Python + FastAPI + LangGraph for the POC**, as briefed. Port to .NET to be reconsidered before production (§8). | Closed |
| D2 | Jira deployment | Unknown. Design supports both; **MVP builds Jira Cloud first**, Data Center is a separate connector. | Yes |
| D3 | Utility application | **Known (2026-11-20):** built by the client; pulls data from Jira via the Jira API and visualises it. Still unknown: its own API surface, auth, whether it caches/syncs, and whether it uses per-user or service-account Jira access. See §2.1. | Yes (for Option A only) |
| D4 | LLM | Azure OpenAI in the client's Azure tenant (aligns with Azure hosting and data residency). Gemini is swappable via LangChain's model interface. | No |
| D5 | User sign-in to our backend | Microsoft Entra ID. | Yes |
| D6 | Business definitions | "Delayed epic", "blocker", "done" are **not defined in the brief**. Defaults proposed in §4.4 — need sign-off. | Yes (for answer correctness) |
| D7 | Persistence | PostgreSQL (Azure Database for PostgreSQL Flexible Server) for encrypted tokens and cached snapshots only. | No |

---

## 1. System overview

```
┌──────────────────────── Chrome extension (MV3, React + TS + Tailwind) ─────────────────────┐
│  Side panel UI: source picker · project picker · chat · report download                     │
│  Service worker: backend API client, session handling                                       │
│  Content script (Option A only): runs on the utility app origin, fetches its API pages      │
└──────────────┬───────────────────────────────────────────────────────┬──────────────────────┘
               │ Option A: raw utility-app JSON pages                   │ chat / report / auth
               ▼                                                        ▼
┌──────────────────────────────────────── Backend (FastAPI) ──────────────────────────────────┐
│  Connectors (source-specific)              │  Shared, source-agnostic                         │
│  ├─ utility_app: mapper (raw → schema)     │  ├─ domain/schema.py  (normalised model)         │
│  ├─ jira_cloud:  OAuth 2.0 + REST client   │  ├─ analytics/        (deterministic functions)  │
│  │               + mapper (raw → schema)   │  ├─ agent/            (LangGraph + tools)        │
│  └─ jira_dc:     (later)                   │  └─ reports/          (OpenPyXL Excel)           │
│                     │                      │            ▲                                     │
│                     └──► ProjectSnapshot ──┴────────────┘                                     │
│  Store: PostgreSQL (encrypted tokens, snapshots with TTL) · Key Vault · App Insights          │
└──────────────────────────────────────────────────────────────────────────────────────────────┘
               │ Option B only
               ▼
        Jira Cloud REST (api.atlassian.com)          Azure OpenAI (tool-calling)
```

**The single seam:** every connector produces a `ProjectSnapshot` (§3). Analytics, agent and reports only ever read a `ProjectSnapshot`; they never import connector code. This is what keeps either integration usable on its own.

---

## 2. How each integration retrieves data

### 2.1 Option A — Utility application (via the extension)

**What we know:** the utility app is client-built and sources its data from the Jira API. Consequences:
- If its API passes Jira-shaped records through (issue keys, `fields.status.statusCategory`, `parent`, sprint fields), the Option A mapper can reuse most of the Jira Cloud mapper; `mapping.yaml` shrinks to the differences.
- Its Jira connection settings tell us whether the client is on Cloud or Data Center (closes D2).
- If it syncs into its own store, answers are only as fresh as its last sync; record the sync time as `fetched_at`.
- If it uses a service account, users may see data beyond their own Jira permissions. Confirm the app applies its own access control.
- Because the client owns it, the preferred route is to ask them for a documented, read-only endpoint (or export) for this purpose, rather than reverse-engineering its internal API.

**Why the extension fetches, not the backend:** the user is already signed in to the utility app in their browser. The backend has no credentials for it, and must not be given the user's session. So the extension fetches using the user's existing session and forwards **response bodies only**.

**Discovery (before any build, with client authorisation):**
1. With the client, open the utility app with DevTools → Network and capture a HAR while loading project, epic, issue and sprint views.
2. Record for each relevant call: URL pattern, method, auth mechanism (cookie / bearer header / other), pagination style (page number, offset, cursor), response shape, and which fields exist.
3. Confirm whether the app offers a supported export (CSV/Excel) or documented API — prefer those over undocumented endpoints.

**Retrieval flow:**
1. User picks "Utility application" in the side panel; the extension checks a tab is open on the configured utility-app origin.
2. Content script (same origin as the app) calls the discovered endpoints with the browser's session, following pagination until exhausted, with a concurrency cap and backoff.
3. Raw pages are posted to `POST /api/v1/sources/utility/ingest` in batches (gzip, size-capped).
4. Backend `utility_app/mapper.py` maps raw records → `ProjectSnapshot` using a field-mapping file (`mapping.yaml`: source path → schema field). This mapping file is the only thing that knows the utility app's shape; nothing depends on its tech stack.

**Fallbacks, in order (each needs client authorisation):** supported export upload → DOM extraction from rendered tables via content script. DOM scraping is brittle (breaks on UI changes, misses paginated/virtualised rows).

**Version 1 (built 2026-11-20, by request): page reading across the tool.** Implemented before API discovery so Option A can be demonstrated without knowing the tool's internals.
- The extension opens the tool in one background tab using the user's sign-in, starting from configured URLs, and follows only same-origin links matching include patterns (exclude patterns block sign-out/edit/delete links). Capped by "max pages".
- On each page it waits for the DOM to settle, reads every HTML table and ARIA grid, and optionally clicks a configured "next page" button for paginated tables. It never clicks anything else.
- Raw tables go to `POST /api/v1/sources/utility/ingest`; `connectors/utility_app/mapper.py` recognises issue tables by header synonyms and issue keys, merges rows for the same issue across pages, and returns warnings for anything it cannot map (unknown statuses, unreadable dates, unmapped columns).
- Known limits: data shown only in charts or cards (not tables) is not read; virtualised grids only expose rendered rows; links handled by JavaScript without an `href` are not followed; sprints, issue links, worklogs and comments are not available, and are marked missing rather than reported as zero.
- Replace or supplement with the tool's API once discovery is done; the backend contract (`ProjectSnapshot`) does not change.

**Version 2 (2026-11-23): Foresight resourcing board and chat.**
- The client's tool is a Foresight resourcing board (static HTML export): per workstream, a month/week grid of outstanding bugs and stories by delivery point, milestones, weekly role allocations (permanent / contract / unknown, flagged when over-allocated) and % focus. It has no issue keys, so it gets its own model, `ResourcingSnapshot` (`domain/schema.py`), and parser (`connectors/utility_app/foresight.py`).
- The page reader now keeps column spans, classed chips inside cells and the headings in scope of each table, which the board parser needs.
- `analytics/resourcing.py` computes over-allocation (weekly total above 100% across workstreams), person schedules, workstream summaries, outstanding work and milestones.
- Chat: `POST /api/v1/chat` answers from an in-memory dataset stored at ingest (`store.py`, shortcut until PostgreSQL). With `LLM_PROVIDER`/`LLM_MODEL` set, a LangGraph agent may only read data through `agent/tools.py`, with an issue-key grounding check and one retry; otherwise a keyword router answers the common questions from the same tools (demo mode, labelled in the UI).
- The floating chat is a content script registered only for the tool's origin; it talks to the backend through the service worker.
- `samples/` holds synthetic data with the client's export structure; `samples/mock-tool/` serves it as a fake Foresight site for demos and tests.

**Risk to validate in discovery:** if the utility app holds its API token only in JavaScript memory (not a cookie), a content script cannot reuse it. In that case the options are a supported export, a service account issued by the client, or DOM extraction.

### 2.2 Option B — Direct Jira Cloud (OAuth 2.0, 3LO)

**Auth flow (backend is the confidential OAuth client; the extension never sees Jira tokens):**
1. Side panel → "Connect Jira" opens `GET /api/v1/auth/jira/start` in a tab. Backend creates a `state` (bound to the signed-in user, single use, 10-min expiry) and redirects to `auth.atlassian.com/authorize`.
2. Atlassian redirects to `GET /api/v1/auth/jira/callback`. Backend validates `state`, exchanges the code, stores access + refresh tokens **encrypted** against the user.
3. Backend calls `GET https://api.atlassian.com/oauth/token/accessible-resources` to get the `cloudId`(s) the user can access.
4. Scopes: `read:jira-work`, `read:jira-user`, `offline_access`, plus the Jira Software scopes needed for boards/sprints. Exact scope list to be confirmed when registering the app in the Atlassian developer console. Read-only only.

**Data retrieval (base `https://api.atlassian.com/ex/jira/{cloudId}`):**

| Data | Endpoint | Notes |
|---|---|---|
| Projects | `GET /rest/api/3/project/search` | Paginated (`startAt`/`maxResults`). Only projects the user can browse are returned. |
| Field catalogue | `GET /rest/api/3/field` | Resolves custom field IDs (Sprint, Story points, Start date, Flagged) per site — never hard-code `customfield_NNNNN`. |
| Issues | `GET/POST /rest/api/3/search/jql` with `project = KEY` | Enhanced search, token pagination (`nextPageToken`). Request only needed `fields`. Epic relation via `parent`. |
| Boards / sprints | `GET /rest/agile/1.0/board?projectKeyOrId=KEY`, `GET /rest/agile/1.0/board/{id}/sprint` | Paginated. |
| Worklogs | Inline on issue; `GET /rest/api/3/issue/{key}/worklog` only when truncated | Fetch lazily. |
| History | Changelog per issue, fetched lazily | Only when a question needs it (e.g. cycle time). |

**Rate limits and resilience:** honour `429` + `Retry-After`; exponential backoff with jitter on `429/5xx`; bounded concurrency (e.g. 4); refresh the access token on `401` once, then fail with a clear "reconnect Jira" error.

**Permissions:** every call uses the user's own token, so Jira's permission scheme is enforced by Jira. Snapshots are cached **per user**, never shared across users.

### 2.3 Jira Data Center (investigate separately)
Different base URL (client-hosted), `/rest/api/2`, `startAt` pagination, auth via Personal Access Token or DC's OAuth 2.0 (version-dependent), plus network reachability from Azure (VPN/private link). Implemented as `connectors/jira_dc/` behind the same interface — no change to analytics, agent or reports.

---

## 3. Common data schema

Pydantic models in `backend/app/domain/schema.py`. Both connectors must produce identical structures for equivalent data — enforced by shared golden-fixture tests (§6).

```python
class StatusCategory(StrEnum): TODO = "todo"; IN_PROGRESS = "in_progress"; DONE = "done"
class IssueKind(StrEnum): EPIC="epic"; STORY="story"; TASK="task"; SUBTASK="subtask"; BUG="bug"; OTHER="other"

class Person(BaseModel):      id: str; display_name: str
class Status(BaseModel):      name: str; category: StatusCategory        # category drives all "done" logic
class Sprint(BaseModel):      id: str; name: str; state: Literal["future","active","closed"]
                              start: date | None; end: date | None; complete: date | None; goal: str | None
class Link(BaseModel):        type: Literal["blocks","is_blocked_by","relates","other"]; target_key: str
class Worklog(BaseModel):     author: Person; started: datetime; seconds: int
class Comment(BaseModel):     author: Person; created: datetime; body: str          # untrusted text
class ChangeEvent(BaseModel): at: datetime; author: Person | None; field: str; from_value: str | None; to_value: str | None

class Issue(BaseModel):
    key: str; url: str                                # traceability: browse link
    kind: IssueKind; raw_type: str                    # normalised + original issue type name
    summary: str; status: Status; priority: str | None
    assignee: Person | None; reporter: Person | None
    epic_key: str | None; parent_key: str | None
    sprint_ids: list[str] = []
    created: datetime; updated: datetime; resolved: datetime | None
    start_date: date | None; due_date: date | None
    story_points: float | None
    flagged: bool = False
    labels: list[str] = []
    links: list[Link] = []
    worklogs: list[Worklog] = []; comments: list[Comment] = []; history: list[ChangeEvent] = []
    extra: dict[str, Any] = {}                        # unmapped custom fields, kept not dropped

class Project(BaseModel):     key: str; name: str; url: str; lead: Person | None

class ProjectSnapshot(BaseModel):
    source: Literal["utility_app","jira_cloud","jira_dc"]
    fetched_at: datetime; as_of: date                 # all "overdue" maths uses as_of, not now()
    project: Project; sprints: list[Sprint]; issues: list[Issue]
    completeness: dict[str, bool]                     # e.g. {"worklogs": False} so answers can say what is missing
```

Notes:
- **Status category, not status name**, decides done/not-done (Jira workflows rename statuses freely). Utility-app mapping must supply a category or a name→category table.
- **Epics are issues** with `kind == EPIC`; epic progress is derived, not stored.
- `completeness` lets the agent say "worklogs were not available from this source" instead of reporting zero.

---

## 4. AI retrieval and analysis

### 4.1 Principle
The LLM **chooses tools and writes prose**. It never calculates, never sees the full dataset, and every fact in an answer must come from a tool result.

### 4.2 Flow (LangGraph)
```
question ──► agent (LLM + tool schemas) ──► tool call(s) ──► deterministic Python over ProjectSnapshot
                 ▲                                                       │ small JSON + evidence keys
                 └──────────────────── results ◄─────────────────────────┘
                 │ final draft
                 ▼
          grounding check ──► pass: answer with cited keys + links
                          └─► fail: one retry with the violations listed, then refuse with "could not verify"
```
MVP uses LangGraph's prebuilt ReAct agent plus one grounding node — no custom multi-agent graph until a need appears.

### 4.3 Tools (`agent/tools.py` → thin wrappers over `analytics/`)
Each returns a compact JSON with `as_of`, the figures, and `evidence: [{key, url}]`, capped at N rows with a `truncated` flag.

| Tool | Answers |
|---|---|
| `project_overview(project)` | Current status, counts by status category, % complete |
| `epic_progress(project, only_delayed=False)` | Epic-wise progress; delayed epics |
| `overdue_issues(project, assignee=None)` | Overdue tasks |
| `blockers(project)` | Blockers and dependencies |
| `sprint_summary(project, sprint="last_closed"\|id)` | Completed in previous sprint, velocity |
| `compare_sprints(project, a, b)` | Sprint comparison |
| `workload(project)` | Outstanding tasks per member |
| `upcoming_deadlines(project, days=14)` | Upcoming due dates |
| `find_issues(project, filters)` | Escape hatch for anything else; filtered, capped |

Multi-project: tools accept a list of project keys; the snapshot store is keyed by `(user, source, project)`.

### 4.4 Proposed definitions (need sign-off — D6)
- **Done:** `status.category == DONE`.
- **Overdue:** `due_date < as_of` and not done.
- **Delayed epic:** epic not done and either its `due_date < as_of`, or any open child issue is overdue.
- **Blocker:** issue not done and (`flagged` or has an `is_blocked_by` link to a not-done issue).
- **% complete:** done child issues ÷ all child issues (story points when ≥ 80 % of children are estimated — threshold to confirm).

### 4.5 Grounding and hallucination controls
- System prompt: use only tool outputs; cite issue keys; say "no data" when a tool returns nothing.
- Grounding check (code, not LLM): every issue key in the answer (`[A-Z][A-Z0-9]+-\d+`) must appear in this turn's tool evidence; every number in the answer must appear in a tool result. Violations trigger one retry, then a safe failure.
- Temperature 0. Answers state `as_of` and the source.

### 4.6 Prompt injection
Issue summaries and comments are user-authored text that reaches the LLM. Mitigations: tools are read-only (worst case is a misleading answer, not an action); comments are excluded by default and only returned, delimited as data, when explicitly asked; grounding check limits fabricated facts.

---

## 5. Stakeholder reports

Built **without the LLM for any figure**: `reports/excel.py` calls the same `analytics/` functions. The LLM only writes the executive summary and "Risks and observations" from those results, and the text passes the same grounding check.

| Sheet | Contents |
|---|---|
| Summary | Project overview, overall progress, executive summary, risks; bar chart (epic % complete), pie (status category); one block per selected project |
| Epics | Key (hyperlink), name, status, % complete, due date, delayed flag, open/done counts |
| Tasks | All non-epic issues: key (hyperlink), type, summary, status, assignee, sprint, due date, overdue flag |
| Blockers | Blocked issue, blocking issue(s), reason (flagged/link), assignee, age |
| Sprints | Per sprint: dates, committed, completed, completion %, carry-over |

Formatting: header styling, freeze panes, auto-filter, column widths, conditional fills by status category and overdue/delayed flags. Download via `GET /api/v1/reports/{id}` (short-lived, per-user).

---

## 6. Folder structure

```
JiraPOC/
├─ docs/ARCHITECTURE.md
├─ backend/
│  ├─ pyproject.toml
│  ├─ app/
│  │  ├─ main.py                     # FastAPI app, middleware, CORS (extension origin only)
│  │  ├─ api/v1/                     # auth.py, sources.py, projects.py, chat.py, reports.py
│  │  ├─ core/                       # config.py, security.py (crypto, session), logging.py
│  │  ├─ domain/schema.py            # §3 — the contract
│  │  ├─ connectors/
│  │  │  ├─ base.py                  # SourceConnector protocol: list_projects(), fetch_snapshot()
│  │  │  ├─ jira_cloud/              # oauth.py, client.py (pagination, retry), mapper.py
│  │  │  └─ utility_app/             # mapper.py, mapping.yaml
│  │  ├─ analytics/metrics.py        # pure functions over ProjectSnapshot
│  │  ├─ agent/                      # graph.py, tools.py, prompts.py, grounding.py
│  │  ├─ reports/excel.py
│  │  └─ store/                      # tokens.py (encrypted), snapshots.py (TTL)
│  └─ tests/
│     ├─ fixtures/                   # jira_cloud/*.json, utility_app/*.json, expected_snapshot.json
│     ├─ test_mappers.py             # both sources → same expected_snapshot.json
│     ├─ test_metrics.py             # definitions in §4.4, edge cases (no due date, empty sprint)
│     ├─ test_grounding.py
│     └─ test_excel.py
└─ extension/
   ├─ manifest.json                  # MV3; host_permissions: backend + utility-app origin only
   ├─ package.json, vite.config.ts, tailwind.config.ts
   └─ src/
      ├─ sidepanel/                  # React app: SourcePicker, ProjectPicker, Chat, Reports
      ├─ background/                 # service worker: API client, session
      └─ content/utilityFetcher.ts   # Option A only
```

Each connector is testable in isolation from recorded fixtures; analytics/agent/reports are tested from `ProjectSnapshot` fixtures with no network.

---

## 7. Security and deployment

### 7.1 Security
- **Secrets:** Jira OAuth client secret, LLM keys and the token-encryption key in **Azure Key Vault**, accessed via managed identity. Nothing secret in the extension bundle.
- **Tokens:** Jira refresh/access tokens encrypted at rest in PostgreSQL; never sent to the extension. Revoke and delete on "Disconnect Jira".
- **User auth to backend:** Entra ID sign-in (D5); backend issues a short-lived session token kept in `chrome.storage.session` (memory only).
- **OAuth hardening:** `state` bound to user, single use, short expiry; exact redirect URI registered; read-only scopes.
- **Option A:** written client authorisation before discovery and build; `host_permissions` limited to the utility-app origin; the extension never reads or exports cookies or tokens, only API response bodies.
- **Authorisation:** snapshots and reports keyed per user; no cross-user cache. Jira permissions enforced by Jira (Option B) or the utility app (Option A).
- **Data protection:** Azure OpenAI in the client's tenant/region (no training on data); send only the fields a tool returns; assignee names are personal data — confirm with the client's DPO. Snapshot TTL (e.g. 24 h) and report file expiry.
- **API:** CORS restricted to the extension ID; per-user rate limiting; request validation (Pydantic); audit log of user, project, question and tool calls (no tokens, no full payloads); OWASP ASVS L2 as the review baseline.
- **Supply chain:** pinned dependencies, Dependabot/pip-audit/npm audit in CI.

### 7.2 Deployment (Azure)
| Component | Target |
|---|---|
| Backend | Container on **Azure Container Apps** (scale to zero for POC), managed identity |
| Database | Azure Database for PostgreSQL Flexible Server, private networking |
| Secrets | Azure Key Vault |
| LLM | Azure OpenAI deployment |
| Observability | Application Insights (OpenTelemetry): request traces, tool-call timings, LLM token usage, grounding failures; alerts on 5xx rate and Jira 429 rate |
| CI/CD | Pipeline: lint, type-check, tests → build image → deploy to staging → smoke test → manual approval → prod; rollback = redeploy previous image revision |
| Extension | Private Chrome Web Store listing or enterprise force-install policy (not public) |

---

## 8. Stack decision (D1) — needs an answer

The brief specifies Python/FastAPI/LangGraph/Pandas/OpenPyXL. The Momentum standard is .NET.

| | Python (brief) | .NET (Momentum standard) |
|---|---|---|
| LangGraph | Native | Not available; use Semantic Kernel or Microsoft.Extensions.AI tool-calling |
| Data / Excel | Pandas, OpenPyXL | LINQ, ClosedXML |
| Team supportability | Separate skill set, separate CI conventions | Fits existing team, tooling and standards |
| POC speed | Faster for agent work | Slightly slower |

**Recommendation:** Python for the POC as the brief asks, keeping the architecture language-neutral (the `ProjectSnapshot` schema and REST API are the contracts). Decide before production whether to port the backend to .NET for long-term supportability. The extension (React + TS) is unaffected either way.

---

## 9. MVP delivery order

1. `schema.py` + fixtures + `analytics/` with tests (no external access needed).
2. Jira Cloud connector (OAuth + fetch + mapper) — needs D2 and an Atlassian developer-console app.
3. Agent with tools + grounding — needs D4.
4. Excel report.
5. Extension side panel: source picker, project picker, chat, download.
6. Utility-app connector — after discovery and authorisation (D3). Can run in parallel with 2–5 once access is granted.

Demo questions from the brief map to: `project_overview` + `epic_progress(only_delayed=True)`, then the report builder.
