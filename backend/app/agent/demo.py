"""Demo mode: answers common questions without an LLM by routing on keywords to the same tools.

Used when no LLM provider is configured, so the chat is demonstrable with zero credentials. Answers are
templated from tool output only, so they are always grounded; the trade-off is a narrow question range.
"""

import re
from datetime import date
from typing import Any

from app.agent.answer import ChatAnswer
from app.agent.tools import MONTHS, ToolError, Toolset
from app.analytics import resourcing
from app.store import Dataset

def suggestions(ds: Dataset) -> list[str]:
    """Example questions the data read can answer, using real names from it."""
    out = ["Give me the current project status and identify delayed epics"] if ds.projects else []
    if rs := ds.resourcing:
        everyone = resourcing.people(rs)
        out.append("Who is over-allocated next week?")
        if everyone:
            out.append(f"What is {everyone[0].split()[0]} working on?")
        if rs.workstreams:
            out.append(f"Tell me about {rs.workstreams[0].name}")
        out.append("Which milestones are coming up?")
    if ds.projects:
        out.append("What are the blockers?")
    return out[:5]


def no_answer(ds: Dataset) -> str:
    """Reply for a question the data cannot answer: what was read, and what can be asked instead."""
    covers = []
    if rs := ds.resourcing:
        covers.append(f"the {rs.title or 'Foresight board'} ({len(rs.workstreams)} workstreams: people, allocations, "
                      "milestones and outstanding work by week)")
    if ds.projects:
        keys = ", ".join(p.project.key for p in ds.projects)
        issues = sum(len(p.issues) for p in ds.projects)
        covers.append(f"{issues} Jira issues in {keys} (status, assignees, due dates and blockers)")
    if not covers:
        return "The pages that were read hold no project data yet. Read the Foresight board or Jira issue pages first."
    lines = [f"I couldn't find that in the pages that were read. They cover {' and '.join(covers)}.",
             "You could ask, for example:", *(f"- {q}" for q in suggestions(ds)[:3])]
    lines.append("If the answer is on another page of the tool, choose that page in the side panel and read again.")
    return "\n".join(lines)


def _d(iso: str | None) -> str:
    if not iso:
        return "no date"
    d = date.fromisoformat(iso[:10])
    return f"{d.day} {d:%b %Y}"


def _work(bugs: int, stories: int, sep: str = ", ") -> str:
    return f"{bugs} bug{'' if bugs == 1 else 's'}{sep}{stories} {'story' if stories == 1 else 'stories'}"


def _has(m: str, *words: str) -> bool:
    return any(re.search(rf"\b{w}", m) for w in words)


def route(ts: Toolset, message: str) -> tuple[str, dict[str, Any]]:
    """Returns (tool name, kwargs). Order matters: specific entities before generic keywords."""
    m = message.lower()
    rs = ts.ds.resourcing
    week = "this" if "this week" in m else "next" if "next week" in m else None
    if ts.ds.projects and (key := re.search(r"\b[A-Z][A-Z0-9_]*-\d+\b", message.upper())):
        if key.group(0) in {i.key for p in ts.ds.projects for i in p.issues}:
            return "issue_details", {"key": key.group(0)}
    wants_tasks = _has(m, "task", "issue", "ticket", "assigned")
    if ts.ds.projects and wants_tasks:
        assignees = {i.assignee.display_name.split()[0].lower() for p in ts.ds.projects for i in p.issues if i.assignee}
        if first := next((n for n in assignees if re.search(rf"\b{re.escape(n)}\b", m)), None):
            return "assigned_issues", {"person": first}
    if rs:
        for person in resourcing.people(rs):
            first = person.split()[0].lower()
            if re.search(rf"\b{re.escape(first)}\b", m):
                return "person_schedule", {"person": person}
        for ws in sorted(rs.workstreams, key=lambda w: -len(w.name)):
            if ws.name.lower() in m:
                return "workstream_details", {"name": ws.name}
        if _has(m, "over-alloc", "overalloc", "over alloc", "overloaded", "stretched", "capacity"):
            return "over_allocated_people", {"week": week}
        if _has(m, "milestone"):
            return "upcoming_milestones", {"week": week}
        if ts.ds.projects and _has(m, "in progress", "to do", "done", "complete"):
            return "project_status", {}
        if _has(m, "outstanding", "bugs", "stories", "delivery point"):
            month = next((mo for mo in MONTHS if re.search(rf"\b{mo}", m)), None)
            year = re.search(r"\b(20\d\d)\b", m)
            return "outstanding_work", {"month": f"{month} {year.group(1)}" if month and year else month}
    if _has(m, "status", "summary", "overview", "update", "how are we", "report"):
        return "project_status", {}
    if ts.ds.projects and _has(m, "delay", "late", "behind", "slipp"):
        return "delayed_epics", {}
    # After the delay check: "Which workstreams are behind?" asks about delay, not for the list.
    if rs and _has(m, "workstreams", "list"):
        return "list_workstreams", {}
    if ts.ds.projects:
        if _has(m, "block", "imped"):
            return "blockers", {}
        if _has(m, "overdue", "past due", "missed"):
            return "overdue_issues", {}
        if _has(m, "workload", "outstanding tasks", "assigned"):
            return "issue_workload", {}
    return "help", {}


def answer(ts: Toolset, message: str) -> ChatAnswer:
    tool, kwargs = route(ts, message)
    if tool == "help":
        return ChatAnswer(text=no_answer(ts.ds), mode="demo")
    try:
        result = getattr(ts, tool)(**kwargs)
    except ToolError as e:
        return ChatAnswer(text=str(e), mode="demo", tools_used=[tool])
    text = FORMATTERS[tool](result, kwargs)
    return ChatAnswer(text=text, evidence=result.get("evidence", []), mode="demo", tools_used=[tool])


# ---------------------------------------------------------------- formatters


def _status(r: dict[str, Any], _: dict[str, Any]) -> str:
    n = len(r["projects"])
    lines = [f"Status of {n} {'project' if n == 1 else 'projects'}" + (" and the resourcing board:" if r.get("board") else ":")]
    for p in r["projects"]:
        pct = "unknown" if p["percent_complete"] is None else f"{p['percent_complete']}%"
        s = p["by_status"]
        lines.append(f"**{p['project']}**: {p['total_issues']} issues, {pct} complete "
                     f"({s['done']} done, {s['in_progress']} in progress, {s['todo']} to do). "
                     f"{p['overdue_issues']} overdue, {p['blocked_issues']} blocked.")
        if p["delayed_epics"]:
            lines += [f"- Delayed epic {e['key']} {e['summary']} ({', '.join(x.replace('_', ' ') for x in e['reasons'])})"
                      for e in p["delayed_epics"]]
        else:
            lines.append("- No delayed epics.")
        if p["missing_data"]:
            lines.append(f"- Not available from the source: {', '.join(p['missing_data'])}.")
    if b := r.get("board"):
        over = b["over_allocated_people_this_and_next_week"]
        lines.append(f"**Resourcing board** ({b['workstreams']} workstreams, {b['people']} people): "
                     f"{b['outstanding_bugs']} bugs and {b['outstanding_stories']} stories outstanding; "
                     f"{len(over)} people over-allocated this or next week"
                     + (f" ({', '.join(over)})" if over else "") + f"; {b['milestones_next_2_weeks']} milestones in the next 2 weeks.")
    return "\n".join(lines)


def _delayed(r: dict[str, Any], _: dict[str, Any]) -> str:
    if not r["epics"]:
        return "No epics are delayed."
    def reason(e: dict[str, Any]) -> str:
        parts = ["past due"] * ("epic_due_date_passed" in e["delay_reasons"])
        if n := len(e["overdue_children"]):
            parts.append(f"{n} overdue {'issue' if n == 1 else 'issues'}")
        return ", ".join(parts)

    n = len(r["epics"])
    return f"{n} delayed {'epic' if n == 1 else 'epics'}:\n" + "\n".join(
        f"- {e['key']} {e['summary']}: {reason(e)} | due {_d(e['due_date'])}, "
        f"{e['children_done']} of {e['children_total']} child issues done"
        + (f"; overdue: {', '.join(c['key'] for c in e['overdue_children'])}" if e["overdue_children"] else "")
        for e in r["epics"])


def _overdue(r: dict[str, Any], _: dict[str, Any]) -> str:
    if not r["issues"]:
        return "No open issues are overdue."
    return f"{len(r['issues'])} overdue issue(s):\n" + "\n".join(
        f"- {i['key']} {i['summary']} ({i['status']}, {i['assignee'] or 'unassigned'}): {i['days_overdue']} days overdue"
        for i in r["issues"])


def _blockers(r: dict[str, Any], _: dict[str, Any]) -> str:
    note = (f"\nNot available from the source: {', '.join(r['not_available_from_source'])}." if r["not_available_from_source"] else "")
    if not r["issues"]:
        return "No blocked issues found." + note
    return f"{len(r['issues'])} blocked issue(s):\n" + "\n".join(
        f"- {i['key']} {i['summary']}: " + ", ".join(
            ["flagged"] * ("flagged" in i["reasons"]) + [f"blocked by {b['key']}" for b in i["blocked_by"]])
        for i in r["issues"]) + note


def _workload(r: dict[str, Any], _: dict[str, Any]) -> str:
    return "Open issues per person:\n" + "\n".join(
        f"- {p['assignee']}: {p['open']} open ({p['in_progress']} in progress, {p['overdue']} overdue)" for p in r["people"])


def _workstreams(r: dict[str, Any], _: dict[str, Any]) -> str:
    return f"{len(r['workstreams'])} workstreams:\n" + "\n".join(f"- {w['name']} ({w['group']})" for w in r["workstreams"])


def _over(r: dict[str, Any], kw: dict[str, Any]) -> str:
    when = {"this": "this week", "next": "next week"}.get(kw.get("week") or "", "from this week on")
    if not r["rows"]:
        return f"Nobody is over-allocated {when}."
    people = sorted({x["person"] for x in r["rows"]})
    lines = [f"{len(people)} {'person' if len(people) == 1 else 'people'} over-allocated {when}:"]
    for x in r["rows"][:12]:
        parts = ", ".join(f"{a['workstream']} {a['percent']}%" for a in x["assignments"])
        lines.append(f"- {x['person']}: {x['total_percent']}% | W/C {_d(x['week'])}: {parts}")
    if len(r["rows"]) > 12:
        lines.append(f"…and {len(r['rows']) - 12} more person-weeks.")
    return "\n".join(lines)


def _person(r: dict[str, Any], _: dict[str, Any]) -> str:
    if not r["weeks"]:
        return f"{r['person']} has no allocations from {_d(r['from_week'])} to {_d(r['to_week'])}."
    lines = [f"{r['person']} ({r['employment']}), {_d(r['from_week'])} to {_d(r['to_week'])}:"]
    for w in r["weeks"]:
        flag = " over-allocated" if w["total_percent"] > 100 else ""
        lines.append(f"- W/C {_d(w['week'])}: {w['total_percent']}%{flag} | "
                     + ", ".join(f"{a['workstream']} {a['percent']}% ({a['role']})" for a in w["assignments"]))
    return "\n".join(lines)


def _workstream(r: dict[str, Any], _: dict[str, Any]) -> str:
    lines = [f"**{r['workstream']}**" + (f" ({r['group']})" if r["group"] else "")]
    if r["note"]:
        lines.append(f"Note: {r['note']}")
    for role, members in r["team"].items():
        lines.append(f"- {role}: " + ", ".join(f"{m['person']} ({m['typical_percent']}%)" for m in members))
    if r["outstanding"]:
        lines.append("Outstanding: " + "; ".join(
            f"{d['label']}: {_work(d['outstanding_bugs'], d['outstanding_stories'])}" for d in r["outstanding"]))
    if r["upcoming_milestones"]:
        lines.append("Upcoming: " + "; ".join(f"{m['label']} (W/C {_d(m['week'])})" for m in r["upcoming_milestones"]))
    return "\n".join(lines)


def _outstanding(r: dict[str, Any], _: dict[str, Any]) -> str:
    scope = f"for {date.fromisoformat(r['month']):%B %Y}" if r["month"] else "across all delivery points"
    if not r["workstreams"]:
        return f"Nothing outstanding {scope}."
    lines = [f"{_work(r['total_bugs'], r['total_stories'], ' and ')} outstanding {scope}:"]
    lines += [f"- {w['workstream']}: {_work(w['bugs'], w['stories'])}" for w in r["workstreams"]]
    return "\n".join(lines)


def _milestones(r: dict[str, Any], _: dict[str, Any]) -> str:
    span = (f"in the week of {_d(r['from_week'])}" if r["from_week"] == r["to_week"]
            else f"from {_d(r['from_week'])} to {_d(r['to_week'])}")
    if not r["milestones"]:
        return f"No milestones {span}."
    return f"Milestones {span}:\n" + "\n".join(
        f"- W/C {_d(m['week'])}: {m['workstream']}, {m['milestone']}" for m in r["milestones"])


def _issue(r: dict[str, Any], _: dict[str, Any]) -> str:
    state = "overdue" if r["overdue"] else r["status"]
    lines = [f"{r['key']} {r['summary']}: {state}"]
    lines += [f"- Type: {r['type']}", f"- Status: {r['status']}", f"- Assignee: {r['assignee'] or 'unassigned'}",
              f"- Due: {_d(r['due_date'])}{' (overdue)' if r['overdue'] else ''}"]
    if r["epic"]:
        lines.append(f"- Epic: {r['epic']}")
    if r["blocked_by"]:
        lines.append(f"- Blocked by: {', '.join(r['blocked_by'])}")
    return "\n".join(lines)


def _assigned(r: dict[str, Any], _: dict[str, Any]) -> str:
    n = len(r["issues"])
    if not n:
        return f"No open Jira issues are assigned to {r['person']}."
    return f"{r['person']} has {n} open {'issue' if n == 1 else 'issues'}:\n" + "\n".join(
        f"- {i['key']} {i['summary']}: {'overdue' if i['overdue'] else i['status']} | due {_d(i['due_date'])}"
        for i in r["issues"])


FORMATTERS = {
    "issue_details": _issue, "assigned_issues": _assigned,
    "project_status": _status, "delayed_epics": _delayed, "overdue_issues": _overdue, "blockers": _blockers,
    "issue_workload": _workload, "list_workstreams": _workstreams, "over_allocated_people": _over,
    "person_schedule": _person, "workstream_details": _workstream, "outstanding_work": _outstanding,
    "upcoming_milestones": _milestones,
}
