"""Deterministic resourcing metrics over a ResourcingSnapshot (who is allocated where, outstanding work).

Like metrics.py, every figure the assistant shows comes from here. Each result carries `evidence`
(workstream + page URL) so answers can cite where the data was read.
"""

from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from app.domain.schema import ResourcingSnapshot, Workstream

FULL_TIME = 100  # a person's weekly allocation above this is over-allocation


def week_of(d: date) -> date:
    return d - timedelta(days=d.weekday())


def _ev(ws: Workstream) -> dict[str, str]:
    return {"label": ws.name, "url": ws.source_url}


def _dedupe(evidence: list[dict[str, str]]) -> list[dict[str, str]]:
    return list({e["label"]: e for e in evidence}.values())


def find_workstream(rs: ResourcingSnapshot, name: str) -> Workstream | None:
    n = name.strip().lower()
    return next((w for w in rs.workstreams if w.name.lower() == n), None) or next(
        (w for w in rs.workstreams if n and n in w.name.lower()), None)


def people(rs: ResourcingSnapshot) -> list[str]:
    return sorted({a.person for w in rs.workstreams for a in w.allocations})


def match_person(rs: ResourcingSnapshot, name: str) -> str | None:
    """Accepts 'Priya', 'Priya D.' or 'priya d'."""
    n = name.strip().lower().rstrip(".")
    everyone = people(rs)
    return next((p for p in everyone if p.lower().rstrip(".") == n), None) or next(
        (p for p in everyone if p.lower().split()[0] == n.split()[0]), None) if n else None


def weeks(rs: ResourcingSnapshot) -> list[date]:
    return sorted({a.week for w in rs.workstreams for a in w.allocations} | {m.week for w in rs.workstreams for m in w.milestones})


def board_overview(rs: ResourcingSnapshot) -> dict[str, Any]:
    this_week = week_of(rs.as_of)
    over = over_allocations(rs, from_week=this_week, to_week=this_week + timedelta(weeks=1))
    upcoming = upcoming_milestones(rs, weeks_ahead=2)
    bugs = sum(d.outstanding_bugs for w in rs.workstreams for d in w.delivery_points)
    stories = sum(d.outstanding_stories for w in rs.workstreams for d in w.delivery_points)
    return {
        "as_of": rs.as_of,
        "title": rs.title,
        "workstreams": len(rs.workstreams),
        "groups": sorted({w.group for w in rs.workstreams if w.group}),
        "people": len(people(rs)),
        "outstanding_bugs": bugs,
        "outstanding_stories": stories,
        "over_allocated_people_this_and_next_week": sorted({o["person"] for o in over["rows"]}),
        "milestones_next_2_weeks": len(upcoming["milestones"]),
        "evidence": [_ev(w) for w in rs.workstreams],
    }


def over_allocations(rs: ResourcingSnapshot, from_week: date | None = None, to_week: date | None = None,
                     person: str | None = None) -> dict[str, Any]:
    """People whose total weekly allocation across workstreams exceeds 100%, or whom the tool flags as over."""
    totals: dict[tuple[str, date], list[tuple[Workstream, str, int, bool]]] = defaultdict(list)
    for ws in rs.workstreams:
        for a in ws.allocations:
            totals[(a.person, a.week)].append((ws, a.role, a.percent, a.over_allocated))
    rows = []
    for (who, week), items in totals.items():
        total = sum(p for _, _, p, _ in items)
        flagged = any(f for *_, f in items)
        if (total <= FULL_TIME and not flagged) or (from_week and week < from_week) or (to_week and week > to_week):
            continue
        if person and who != person:
            continue
        rows.append({
            "person": who, "week": week, "total_percent": total, "flagged_by_tool": flagged,
            "assignments": [{"workstream": ws.name, "role": role, "percent": p} for ws, role, p, _ in items],
            "_ev": [_ev(ws) for ws, *_ in items],
        })
    rows.sort(key=lambda r: (r["week"], -r["total_percent"], r["person"]))
    evidence = _dedupe([e for r in rows for e in r.pop("_ev")])
    return {"from_week": from_week, "to_week": to_week, "rows": rows, "evidence": evidence}


def person_schedule(rs: ResourcingSnapshot, person: str, from_week: date | None = None, weeks_ahead: int = 4) -> dict[str, Any]:
    start = from_week or week_of(rs.as_of)
    end = start + timedelta(weeks=weeks_ahead - 1)
    by_week: dict[date, list[dict[str, Any]]] = defaultdict(list)
    evidence = []
    for ws in rs.workstreams:
        for a in ws.allocations:
            if a.person == person and start <= a.week <= end:
                by_week[a.week].append({"workstream": ws.name, "role": a.role, "percent": a.percent})
                evidence.append(_ev(ws))
    schedule = [{"week": w, "total_percent": sum(x["percent"] for x in items), "assignments": items}
                for w, items in sorted(by_week.items())]
    employment = next((a.employment for ws in rs.workstreams for a in ws.allocations if a.person == person), "unknown")
    return {"person": person, "employment": employment, "from_week": start, "to_week": end,
            "weeks": schedule, "evidence": _dedupe(evidence)}


def workstream_summary(rs: ResourcingSnapshot, ws: Workstream) -> dict[str, Any]:
    team: dict[str, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    for a in ws.allocations:
        team[a.role][a.person].append(a.percent)
    this_week = week_of(rs.as_of)
    return {
        "workstream": ws.name,
        "group": ws.group,
        "note": ws.note,
        "team": {role: [{"person": p, "typical_percent": max(set(v), key=v.count), "weeks_allocated": len(v)}
                        for p, v in sorted(members.items())] for role, members in team.items()},
        "outstanding": [d.model_dump() for d in ws.delivery_points if d.outstanding_bugs or d.outstanding_stories],
        "upcoming_milestones": [m.model_dump() for m in ws.milestones if m.week >= this_week][:6],
        "focus_this_week": ws.focus.get(this_week),
        "evidence": [_ev(ws)],
    }


def outstanding_work(rs: ResourcingSnapshot, month: date | None = None) -> dict[str, Any]:
    """Outstanding bugs/stories per workstream, for one delivery month or all."""
    rows = []
    for ws in rs.workstreams:
        points = [d for d in ws.delivery_points if month is None or d.month == month]
        bugs, stories = sum(d.outstanding_bugs for d in points), sum(d.outstanding_stories for d in points)
        if bugs or stories:
            rows.append({"workstream": ws.name, "bugs": bugs, "stories": stories, "_ws": ws})
    rows.sort(key=lambda r: (-(r["bugs"] + r["stories"]), r["workstream"]))
    evidence = [_ev(r.pop("_ws")) for r in rows]
    return {"month": month, "total_bugs": sum(r["bugs"] for r in rows), "total_stories": sum(r["stories"] for r in rows),
            "workstreams": rows, "evidence": evidence}


def upcoming_milestones(rs: ResourcingSnapshot, weeks_ahead: int = 4, start: date | None = None) -> dict[str, Any]:
    start = start or week_of(rs.as_of)
    end = start + timedelta(weeks=weeks_ahead - 1)
    rows = sorted(
        ({"week": m.week, "workstream": ws.name, "milestone": m.label, "_ws": ws}
         for ws in rs.workstreams for m in ws.milestones if start <= m.week <= end),
        key=lambda r: (r["week"], r["workstream"], r["milestone"]),
    )
    evidence = _dedupe([_ev(r.pop("_ws")) for r in rows])
    return {"from_week": start, "to_week": end, "milestones": rows, "evidence": evidence}
