"""Generate synthetic, client-safe sample data with the same structure as the client's exports.

Outputs (all invented: Doe surnames, made-up keys, IDs, projects and workstreams):
  samples/jira-sample.csv            same 283 columns as the client's Jira CSV export (jira-columns.json)
  samples/mock-tool/board.html       same markup/CSS as the Foresight board export
  samples/mock-tool/issues.html      the CSV's key fields as tables, for multi-page extraction tests
  samples/mock-tool/index.html       landing page linking both

Run:  python samples/generate_samples.py      (deterministic: same output every run)
"""

import csv
import html
import json
import random
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).parent
rng = random.Random(20261123)
EXPORT_AT = datetime(2026, 11, 23, 10, 15, 0)

# ---------------------------------------------------------------- people & projects

FIRST_NAMES = ["Priya", "Marcus", "Elena", "Tomasz", "Aisha", "Callum", "Ines", "Rahul", "Freya", "Kwame",
               "Sofia", "Owen", "Mei", "Darius", "Lucia", "Hamish", "Zara", "Felix"]
EMPLOYMENT = ["permanent"] * 10 + ["contract"] * 6 + ["unknown"] * 2


def account_id() -> str:
    return f"712020:{uuid.UUID(int=rng.getrandbits(128))}"


PEOPLE = [{"name": f"{n} Doe", "short": f"{n} D.", "id": account_id(), "employment": e}
          for n, e in zip(FIRST_NAMES, EMPLOYMENT)]
rng.shuffle(PEOPLE)

PROJECTS = [
    {"key": "K41", "name": "K41 : Harbourline Logistics (Contract/SOW)", "account": "A7710 - Harbourline Logistics (Contract / SOW)"},
    {"key": "K42", "name": "K42 : Harbourline Retail (Contract/SOW)", "account": "A7711 - Harbourline Retail (Contract / SOW)"},
    {"key": "M07", "name": "M07 : Saffron Platform (Internal/BAU)", "account": "A7720 - Saffron Platform (Internal / BAU)"},
    {"key": "T19", "name": "T19 : Supplier Onboarding (Contract/SOW)", "account": "A7730 - Supplier Onboarding (Contract / SOW)"},
]
for p in PROJECTS:
    p["lead"] = rng.choice(PEOPLE[:4])
    p["description"] = (f"Harbourline Group, a.k.a. HLG, are a fictional client used for demonstrations.\n\n"
                        f"Account owner is:\nHarbourline - {p['account'].split(' - ')[0]} - HLG: Demo _Owner_ <demo.owner@example.com>")

WORKSTREAMS = [
    ("Project Saffron", "Stock Sync", "Two stories at risk of slipping. 1 bug open on staging awaiting supplier data refresh."),
    ("Project Saffron", "Supplier Portal", None),
    ("Project Saffron", "Label Printing", "Printer firmware upgrade blocks two stories until mid-December."),
    ("Project Saffron", "Recall Tracker", None),
    ("Project Saffron", "Allergen Matrix", "Awaiting sign-off on the revised allergen categories from the client."),
    ("Project Saffron", "Order Hub", None),
    ("Project Saffron", "Pricing Engine", None),
    ("Project Saffron", "Waste Reporting", "New reporting scope agreed; estimates to follow."),
    ("Project Saffron", "Audit Trail", None),
    ("Project Saffron", "Driver App", None),
    ("Project Saffron", "Customer Returns", "Returns flow depends on Order Hub API changes."),
    ("Project Saffron", "Batch Traceability", None),
    ("Project Saffron", "Data Migration", None),
    ("Other workstreams", "BAU Support", "Rota covers out-of-hours support for all live services."),
]

# ---------------------------------------------------------------- board timeline

WINDOW_START = date(2026, 11, 23)  # first W/C in the planning window
WEEKS = [WINDOW_START + timedelta(weeks=i) for i in range(10)]
PAST_MONTHS = [date(2026, 7, 1), date(2026, 8, 1), date(2026, 9, 1), date(2026, 10, 1)]
MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def month_label(d: date) -> str:
    return f"{MONTH_ABBR[d.month - 1]} &#39;{d.year % 100:02d}"


ROLES = ["Scrum Master", "F&B Specialist", "Lead Developer(s)", "Developer(s)", "Tester(s)"]
MILESTONES = ["Onsite testing", "Dev focus - onsite bugs", "Original Dev", "UAT sign-off", "Go-live"]


def build_board():
    """Workstreams with month columns, outstanding counts, milestones and weekly allocations."""
    board = []
    load = defaultdict(int)  # (person, week) -> % already allocated; keeps most people within 100%
    for group, name, note in WORKSTREAMS:
        past = sorted(rng.sample(PAST_MONTHS, rng.randint(0, 4)))
        team = {
            "Scrum Master": [rng.choice(PEOPLE[:3])],
            "F&B Specialist": rng.sample(PEOPLE[3:6], rng.randint(0, 1)),
            "Lead Developer(s)": [rng.choice(PEOPLE[6:10])],
            "Developer(s)": rng.sample(PEOPLE[8:15], rng.randint(1, 3)),
            "Tester(s)": rng.sample(PEOPLE[14:18], rng.randint(1, 2)),
        }
        alloc = defaultdict(dict)  # (role, person name) -> {week: percent}
        for role, people in team.items():
            for person in people:
                pct = rng.choice([20, 25, 50, 50, 100] if role in ("Developer(s)", "Lead Developer(s)") else [20, 25, 40, 50])
                for w in WEEKS:
                    fits = load[(person["name"], w)] + pct <= 100
                    if rng.random() < 0.78 and (fits or rng.random() < 0.08):  # occasional over-allocation, as on real boards
                        alloc[(role, person["name"])][w] = pct
                        load[(person["name"], w)] += pct
        milestones = {w: rng.sample(MILESTONES, rng.choice([1, 1, 2])) for w in WEEKS if rng.random() < 0.22}
        counts = {m: (rng.randint(0, 3), rng.randint(0, 9)) for m in past + [date(2026, 11, 1), date(2026, 12, 1), date(2027, 1, 1)]}
        board.append({"group": group, "name": name, "note": note, "past": past, "team": team, "alloc": alloc,
                      "milestones": milestones, "counts": counts, "unscheduled": rng.random() < 0.8,
                      "unscheduled_counts": (rng.randint(0, 2), rng.randint(0, 6)), "focus": rng.choice([35, 45, 50, 60])})

    # Over-allocation: a person whose total across all workstreams exceeds 100% in a week.
    totals = defaultdict(int)
    for ws in board:
        for (_, person), weeks in ws["alloc"].items():
            for w, pct in weeks.items():
                totals[(person, w)] += pct
    return board, {k for k, v in totals.items() if v > 100}


BOARD_CSS = (ROOT / "foresight-board.css").read_text(encoding="utf-8")
BOARD_SCRIPT = ('(function(){var q=document.getElementById("q"),items=Array.prototype.slice.call(document.querySelectorAll(".rpt-ws")),'
                'countEl=document.getElementById("count");function apply(){var term=q.value.trim().toLowerCase();var shown=0;'
                'items.forEach(function(el){var show=!term||el.dataset.name.indexOf(term)!==-1;el.classList.toggle("hidden",!show);'
                'if(show)shown++;});countEl.textContent=shown+" of "+items.length+" shown";}q.addEventListener("input",apply);apply();})();')


def render_board(board, over) -> str:
    e = html.escape
    out = [f'<!DOCTYPE html><html><head><meta charset="utf-8"><title>Foresight Board — Saffron</title><style>{BOARD_CSS}</style></head><body>',
           '<h1>Foresight Board — Saffron</h1>',
           f'<div class="meta">Exported {EXPORT_AT.strftime("%a %b %d %Y %H:%M:%S")} GMT+0000 (Greenwich Mean Time) · {len(board)} workstreams</div>',
           '<div class="legend"><span><span class="dot permanent"></span>Permanent</span><span><span class="dot contract"></span>Contract</span>'
           '<span><span class="dot unknown"></span>Unknown</span><span>|</span><span style="color:var(--accent-red);font-weight:700">Red</span>'
           '<span>= over-allocated that week</span></div>',
           '<div class="toolbar"><input type="text" id="q" placeholder="Search workstream..."><button type="button" onclick="window.print()">🖨 Print</button><span id="count"></span></div>']
    current_group = None
    for ws in board:
        if ws["group"] != current_group:
            current_group = ws["group"]
            out.append(f'<div class="rpt-group-hdr">{e(current_group)}</div>')
        # Columns: past months (1 col each), window months (1 col per week), Unscheduled.
        months = [(m, [None]) for m in ws["past"]]
        for m in (date(2026, 11, 1), date(2026, 12, 1), date(2027, 1, 1)):
            months.append((m, [w for w in WEEKS if (w.year, w.month) == (m.year, m.month)]))
        cols = [(i % 2, m, w) for i, (m, weeks) in enumerate(months) for w in weeks]
        unsched_mg = len(months) % 2
        out.append(f'<div class="rpt-ws" data-name="{e(ws["name"].lower())}"><div class="rpt-ws-hdr">{e(ws["name"])}</div>')
        if ws["note"]:
            out.append(f'<div class="rpt-ws-note">{e(ws["note"])}</div>')
        out.append('<div class="rpt-tblwrap"><table class="rpt-grid"><thead><tr><th class="rowlbl">Delivery Point</th>')
        for i, (m, weeks) in enumerate(months):
            out.append(f'<th colspan="{len(weeks)}" class="mhdr mg-{i % 2}">{month_label(m)}</th>')
        if ws["unscheduled"]:
            out.append(f'<th colspan="1" class="mhdr mg-{unsched_mg}">Unscheduled</th>')
        out.append("</tr></thead><tbody>")

        def count_html(bugs, stories):
            return (f'<span class="cbug">{bugs} bug{"" if bugs == 1 else "s"}</span>'
                    f'<span class="cstory">{stories} {"story" if stories == 1 else "stories"}</span>')

        row = ['<tr><td class="rowlbl">Outstanding</td>']
        for i, (m, weeks) in enumerate(months):
            row.append(f'<td colspan="{len(weeks)}" class="mg-{i % 2} mg-start cnt">{count_html(*ws["counts"][m])}</td>')
        if ws["unscheduled"]:
            row.append(f'<td colspan="1" class="mg-{unsched_mg} mg-start cnt">{count_html(*ws["unscheduled_counts"])}</td>')
        out.append("".join(row) + "</tr>")

        def week_row(label, render, header=False):
            tag, base = ("th", "wkhdr ") if header else ("td", "")
            r = [f'<tr><td class="rowlbl">{e(label)}</td>']
            prev_m = None
            for mg, m, w in cols:
                start = " mg-start" if m != prev_m else ""
                r.append(f'<{tag} class="{base}mg-{mg}{start}">{"—" if w is None else render(w)}</{tag}>')
                prev_m = m
            if ws["unscheduled"]:
                r.append(f'<{tag} class="{base}mg-{unsched_mg} mg-start">—</{tag}>')
            return "".join(r) + "</tr>"

        out.append(week_row("W/C", lambda w: w.strftime("%d/%m/%Y"), header=True))
        out.append(week_row("Tasks / Milestones",
                            lambda w: "".join(f'<span class="mchip">{e(t)}</span>' for t in ws["milestones"].get(w, []))))
        for role in ROLES:
            def chips(w, role=role):
                parts = []
                for person in ws["team"][role]:
                    pct = ws["alloc"].get((role, person["name"]), {}).get(w)
                    if pct:
                        over_cls = " over" if (person["name"], w) in over else ""
                        parts.append(f'<span class="pchip fs-emp-{person["employment"]}{over_cls}">{e(person["short"])} {pct}%</span>')
                return "".join(parts)
            out.append(week_row(role, chips))
        out.append(week_row("% Focus", lambda w: f'{ws["focus"]}% Stories'))
        out.append("</tbody></table></div></div>")
    out.append(f"<script>{BOARD_SCRIPT}</script></body></html>")
    return "".join(out)


# ---------------------------------------------------------------- Jira CSV

STATUSES = [("To Do", "To Do")] * 12 + [("Awaiting Information", "To Do"), ("Ready For Development", "To Do"),
            ("Ready For Development", "To Do"), ("In Development", "In Progress"), ("In Development", "In Progress"),
            ("In Development", "In Progress"), ("Ready For CAB", "In Progress"), ("Post Development", "In Progress"),
            ("In Testing", "In Progress"), ("In Testing", "In Progress"), ("Done", "Done"), ("Done", "Done"),
            ("Done", "Done"), ("Done", "Done")]
STORY_VERBS = ["Validate", "Display", "Export", "Import", "Recalculate", "Archive", "Notify on", "Audit", "Sync", "Filter"]
STORY_OBJECTS = ["supplier batch codes", "allergen flags", "returns reasons", "driver shift times", "price overrides",
                 "waste categories", "stock adjustments", "label templates", "recall notices", "order cut-off times"]
STORY_SUFFIX = ["in the portal", "on the dashboard", "for store users", "via the nightly job", "in the mobile app"]


def jira_dt(d: datetime) -> str:
    hour = d.hour % 12 or 12
    return f"{d.day:02d}/{d.strftime('%b')}/{d.year % 100:02d} {hour}:{d.minute:02d} {'AM' if d.hour < 12 else 'PM'}"


def build_issues(board):
    epics_ws = [ws for ws in board if ws["group"] == "Project Saffron"][:9]
    epics = []
    for i, ws in enumerate(epics_ws):
        project = PROJECTS[i % len(PROJECTS)]
        status = rng.choice(["In Progress", "In Progress", "To Do", "Done"])
        epics.append({"key": f"{project['key']}-{410 + i * 7}", "id": str(2_100_000 + i), "project": project,
                      "summary": f"{ws['name']} - Feature Delivery Programme", "status": status,
                      "due": date(2026, 11, 13) + timedelta(days=14 * rng.randint(0, 6)) if status != "Done" else None})
    issues = []
    for n in range(30):
        epic = epics[n % len(epics)]
        project = epic["project"]
        status, category = STATUSES[n % len(STATUSES)]
        created = EXPORT_AT - timedelta(days=rng.randint(10, 120), hours=rng.randint(0, 9), minutes=rng.randint(0, 59))
        updated = created + (EXPORT_AT - created) * rng.random()
        issues.append({
            "key": f"{project['key']}-{3100 + n * 13 + rng.randint(0, 9)}", "id": str(4_800_000 + n * 37), "project": project,
            "epic": epic, "status": status, "category": category,
            "summary": f"{rng.choice(STORY_VERBS)} {rng.choice(STORY_OBJECTS)} {rng.choice(STORY_SUFFIX)}",
            "priority": rng.choice(["Medium"] * 6 + ["Highest", "High", "Low"]),
            "assignee": rng.choice(PEOPLE), "reporter": rng.choice(PEOPLE[:6]),
            "created": created, "updated": updated,
            "due": (date(2026, 11, 9) + timedelta(days=7 * rng.randint(0, 8))) if rng.random() < 0.35 else None,
            "delivery_point": rng.choice(["Nov 2026", "Dec 2026", "Jan 2027"]) if rng.random() < 0.4 else "",
            "worklogs": [(rng.choice(PEOPLE), created + timedelta(days=rng.randint(1, 9)), rng.choice([900, 1800, 3600, 7200]))
                         for _ in range(rng.choice([0, 0, 1, 1, 2, 4]))],
        })
    for issue in rng.sample(issues, 6):  # a few blocking relationships, all within the sample
        blocker = rng.choice([i for i in issues if i is not issue])
        issue["blocked_by"] = blocker["key"]
    return epics, issues


def write_csv(issues):
    headers = json.loads((ROOT / "jira-columns.json").read_text(encoding="utf-8"))
    rows = []
    for issue in issues:
        values: dict[str, list[str]] = defaultdict(list)
        put = lambda col, *vals: values[col].extend(vals)  # noqa: E731
        p, a, r = issue["project"], issue["assignee"], issue["reporter"]
        put("Summary", issue["summary"]); put("Issue key", issue["key"]); put("Issue id", issue["id"])
        put("Issue Type", "Story"); put("Status", issue["status"]); put("Project key", p["key"])
        put("Project name", p["name"]); put("Project type", "software")
        put("Project lead", p["lead"]["name"]); put("Project lead id", p["lead"]["id"])
        if rng.random() < 0.4:
            put("Project description", p["description"])
        put("Priority", issue["priority"])
        put("Assignee", a["name"]); put("Assignee Id", a["id"])
        put("Reporter", r["name"]); put("Reporter Id", r["id"]); put("Creator", r["name"]); put("Creator Id", r["id"])
        put("Created", jira_dt(issue["created"])); put("Updated", jira_dt(issue["updated"]))
        if issue["due"]:
            put("Due date", jira_dt(datetime.combine(issue["due"], datetime.min.time())))
        put("Votes", "0")
        put("Labels", *rng.sample(["saffron", "phase_two", "store_rollout", "supplier_facing"], rng.choice([0, 0, 1, 2])))
        put("Description", "Implement as agreed; the acceptance criteria are in the attached document.")
        watchers = [r] + rng.sample(PEOPLE, rng.choice([0, 0, 1, 2]))
        put("Watchers", *[w["name"] for w in watchers]); put("Watchers Id", *[w["id"] for w in watchers])
        spent = 0
        for who, when, secs in issue["worklogs"]:
            put("Log Work", f"Dev-progress;{jira_dt(when)};{who['id']};{secs}")
            spent += secs
        if spent:
            put("Time Spent", str(spent)); put("Σ Time Spent", str(spent))
        if issue.get("blocked_by"):
            put("Inward issue link (Blocks)", issue["blocked_by"])
        put("Inward issue link (Test)", f"{p['key']}-{9000 + int(issue['id']) % 997}")
        put("Custom field (Account)", p["account"])
        put("Custom field (Approvals)", "ApprovalsCFValue{approvals=[]}")
        if issue["delivery_point"]:
            put("Custom field (Delivery Point)", issue["delivery_point"])
        dev = rng.choice(PEOPLE)
        if rng.random() < 0.3:
            put("Custom field (Developer)", dev["name"]); put("Custom field (Developer)Id", dev["id"])
        put("Custom field (Development)", "{}")
        lead = rng.choice(PEOPLE)
        if rng.random() < 0.3:
            put("Custom field (Lead Developer)", lead["name"]); put("Custom field (Lead Developer)Id", lead["id"])
        if rng.random() < 0.15:
            put("Custom field (MoSCoW)", rng.choice(["Must Have", "Should Have", "Could Have"]))
        put("Custom field (Rank)", f"0|i{rng.randint(10, 99)}{rng.choice('abcdefgh')}{rng.choice('xyz')}:")
        if rng.random() < 0.3:
            put("Custom field (StoryType)", rng.choice(["Requirement Gap", "Change Request", "Original Scope"]))
        ta = rng.choice(PEOPLE)
        if rng.random() < 0.3:
            put("Custom field (Technical Analyst)", ta["name"]); put("Custom field (Technical Analyst)Id", ta["id"])
        put("Custom field (Test Automation)", "Manual")
        if rng.random() < 0.5:
            put("Comment", f"{jira_dt(issue['updated'])};{rng.choice(PEOPLE)['id']};Demo comment: progress reviewed at stand-up.")
        put("Parent", issue["epic"]["id"]); put("Parent key", issue["epic"]["key"]); put("Parent summary", issue["epic"]["summary"])
        put("Status category", issue["category"])
        put("Status category changed", jira_dt(issue["updated"]))

        used = defaultdict(int)
        row = []
        for h in headers:
            vals = values.get(h, [])
            row.append(vals[used[h]] if used[h] < len(vals) else "")
            used[h] += 1
        for h, vals in values.items():
            assert h in headers, f"unknown column {h}"
            assert len(vals) <= headers.count(h), f"too many values for {h}"
        rows.append(row)
    with open(ROOT / "jira-sample.csv", "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(headers)
        w.writerows(rows)


def render_issues_page(epics, issues) -> str:
    e = html.escape
    # Keys are plain text: no external Jira address is invented for the demo.
    epic_rows = "".join(
        f"<tr><td>{x['key']}</td><td>{e(x['summary'])}</td><td>Epic</td><td>{x['status']}</td>"
        f"<td>{x['due'].strftime('%d/%m/%Y') if x['due'] else ''}</td></tr>" for x in epics)
    issue_rows = "".join(
        f"<tr><td>{i['key']}</td><td>{e(i['summary'])}</td><td>Story</td><td>{e(i['status'])}</td><td>{i['category']}</td>"
        f"<td>{e(i['priority'])}</td><td>{e(i['assignee']['name'])}</td><td>{i['epic']['key']}</td><td>{i['delivery_point']}</td>"
        f"<td>{i['due'].strftime('%d/%m/%Y') if i['due'] else ''}</td><td>{i.get('blocked_by', '')}</td></tr>" for i in issues)
    return (f'<!DOCTYPE html><html><head><meta charset="utf-8"><title>Foresight — Jira issues</title><style>{BOARD_CSS}'
            '.rpt-grid td{text-align:left}</style></head><body><h1>Foresight — Jira issues</h1>'
            f'<div class="meta">Synced {EXPORT_AT.strftime("%a %b %d %Y %H:%M")} · {len(issues)} stories · <a href="index.html">Home</a></div>'
            '<div class="rpt-ws"><div class="rpt-ws-hdr">Epics</div><div class="rpt-tblwrap"><table class="rpt-grid"><thead><tr>'
            '<th>Key</th><th>Summary</th><th>Issue Type</th><th>Status</th><th>Due date</th></tr></thead>'
            f'<tbody>{epic_rows}</tbody></table></div></div>'
            '<div class="rpt-ws"><div class="rpt-ws-hdr">Stories</div><div class="rpt-tblwrap"><table class="rpt-grid"><thead><tr>'
            '<th>Issue key</th><th>Summary</th><th>Issue Type</th><th>Status</th><th>Status category</th><th>Priority</th>'
            '<th>Assignee</th><th>Parent key</th><th>Delivery Point</th><th>Due date</th><th>Blocked by</th></tr></thead>'
            f'<tbody>{issue_rows}</tbody></table></div></div></body></html>')


INDEX = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>Foresight</title><style>{{css}}
.home a{{display:block;padding:.8rem 1rem;margin:.5rem 0;border:1px solid var(--border);border-radius:8px;color:var(--text-primary);text-decoration:none;background:var(--bg-card)}}
.home a:hover{{border-color:var(--accent-indigo)}}</style></head><body><h1>Foresight</h1>
<div class="meta">Demo instance with synthetic data · all names and IDs are invented</div>
<nav class="home"><a href="board.html">Foresight Board — Saffron</a><a href="issues.html">Jira issues</a></nav></body></html>"""


def main() -> None:
    board, over = build_board()
    epics, issues = build_issues(board)
    write_csv(issues)
    out = ROOT / "mock-tool"
    out.mkdir(exist_ok=True)
    (out / "board.html").write_text(render_board(board, over), encoding="utf-8")
    (out / "issues.html").write_text(render_issues_page(epics, issues), encoding="utf-8")
    (out / "index.html").write_text(INDEX.replace("{css}", BOARD_CSS), encoding="utf-8")
    print(f"{len(board)} workstreams, {len(over)} over-allocated person-weeks, {len(epics)} epics, {len(issues)} stories")


if __name__ == "__main__":
    main()
