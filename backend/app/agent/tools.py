"""The only way the assistant reads data: small, deterministic functions over one Dataset.

Used directly by demo mode and wrapped as LLM tools in llm.py. Every result is JSON-safe and carries
`evidence`: [{label, url}] — issue keys or workstream names with the page they were read from.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any

from fastapi.encoders import jsonable_encoder

from app.analytics import metrics, resourcing
from app.store import Dataset

MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]


class ToolError(ValueError):
    """Raised for input the user can fix (unknown person, unknown workstream); shown to the user/LLM as-is."""


def _issue_ev(result: dict[str, Any]) -> list[dict[str, str]]:
    return [{"label": e["key"], "url": e["url"]} for e in result.pop("evidence", [])]


def parse_week(value: str | None, as_of: date) -> date | None:
    """'this', 'next', 'YYYY-MM-DD' or 'DD/MM/YYYY' -> the Monday of that week."""
    if not value:
        return None
    v = value.strip().lower()
    this = resourcing.week_of(as_of)
    if v in ("this", "this week", "current"):
        return this
    if v in ("next", "next week"):
        return this + timedelta(weeks=1)
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return resourcing.week_of(datetime.strptime(v, fmt).date())
        except ValueError:
            continue
    raise ToolError(f"Could not read the week '{value}'. Use 'this', 'next' or a date like 2026-11-30.")


def parse_month(value: str | None, as_of: date) -> date | None:
    """'Nov', 'November 2026', 'Nov '26', '2026-11' -> first of month."""
    if not value:
        return None
    v = value.strip().lower()
    if m := re.match(r"^(\d{4})-(\d{1,2})$", v):
        return date(int(m.group(1)), int(m.group(2)), 1)
    m = re.match(r"^([a-z]{3})[a-z]*\.?\s*['’]?\s*(\d{2}|\d{4})?$", v)
    if not m or m.group(1) not in MONTHS:
        raise ToolError(f"Could not read the month '{value}'. Use e.g. 'Nov 2026'.")
    month = MONTHS.index(m.group(1)) + 1
    if m.group(2):
        year = int(m.group(2))
        year = year + 2000 if year < 100 else year
    else:  # no year: the next occurrence of that month from as_of (or this month)
        year = as_of.year if month >= as_of.month else as_of.year + 1
    return date(year, month, 1)


@dataclass
class Tool:
    name: str
    description: str
    fn: Callable[..., dict[str, Any]]


class Toolset:
    def __init__(self, ds: Dataset):
        self.ds = ds

    # ---- helpers
    def _projects(self, project: str | None):
        if not project:
            return self.ds.projects
        chosen = [p for p in self.ds.projects if project.strip().upper() in (p.project.key, p.project.name.upper())]
        # Small models often invent a project argument; answering for all projects beats failing the question.
        return chosen or self.ds.projects

    def _board(self):
        if self.ds.resourcing is None:
            raise ToolError("No resourcing board was read in this scan, so allocation questions cannot be answered.")
        return self.ds.resourcing

    @staticmethod
    def _out(result: dict[str, Any], evidence: list[dict[str, str]]) -> dict[str, Any]:
        return jsonable_encoder({**result, "evidence": evidence})

    # ---- project (Jira issue) tools
    def project_status(self, project: str | None = None) -> dict[str, Any]:
        """Overall status: issue counts, % complete, delayed epics, overdue and blocked counts per project, plus the board headline."""
        rows, evidence = [], []
        for snap in self._projects(project):
            overview = metrics.project_overview(snap)
            delayed = metrics.epic_progress(snap, only_delayed=True)
            evidence += _issue_ev(delayed)
            overview["delayed_epics"] = [{"key": e["key"], "summary": e["summary"], "reasons": e["delay_reasons"]} for e in delayed["epics"]]
            rows.append(overview)
        board = None
        if self.ds.resourcing and not project:
            board = resourcing.board_overview(self.ds.resourcing)
            board.pop("evidence")  # headline only; detail tools cite their own workstreams
        if not rows and board is None:
            raise ToolError("The scan found no projects or board data.")
        return self._out({"projects": rows, "board": board}, evidence)

    def delayed_epics(self, project: str | None = None) -> dict[str, Any]:
        """Epics that are not done and are past their due date or have overdue child issues."""
        rows, evidence = [], []
        for snap in self._projects(project):
            r = metrics.epic_progress(snap, only_delayed=True)
            evidence += _issue_ev(r)
            rows += [{**e, "project": snap.project.key} for e in r["epics"]]
        return self._out({"epics": rows}, evidence)

    def overdue_issues(self, project: str | None = None) -> dict[str, Any]:
        """Open issues whose due date has passed, most overdue first."""
        rows, evidence = [], []
        for snap in self._projects(project):
            r = metrics.overdue_issues(snap)
            evidence += _issue_ev(r)
            rows += r["issues"]
        rows.sort(key=lambda i: (-i["days_overdue"], i["key"]))  # most overdue first across projects
        return self._out({"issues": rows}, evidence)

    def blockers(self, project: str | None = None) -> dict[str, Any]:
        """Open issues that are flagged or blocked by another open issue."""
        rows, evidence, missing = [], [], set()
        for snap in self._projects(project):
            r = metrics.blockers(snap)
            evidence += _issue_ev(r)
            rows += r["issues"]
            missing |= {k for k in ("links", "flags") if not snap.completeness.get(k, True)}
        return self._out({"issues": rows, "not_available_from_source": sorted(missing)}, evidence)

    def issue_workload(self, project: str | None = None) -> dict[str, Any]:
        """Open Jira issues per assignee (counts, in progress, overdue)."""
        people, evidence = [], []
        for snap in self._projects(project):
            r = metrics.workload(snap)
            evidence += [{"label": e["key"], "url": e["url"]} for e in r["evidence"]]
            people += [{k: v for k, v in p.items() if k != "issues"} | {"project": snap.project.key} for p in r["people"]]
        return self._out({"people": people}, evidence)

    # ---- resourcing (board) tools
    def list_workstreams(self) -> dict[str, Any]:
        """All workstreams on the resourcing board with their group."""
        rs = self._board()
        return self._out({"workstreams": [{"name": w.name, "group": w.group} for w in rs.workstreams],
                          "people": resourcing.people(rs)}, [])

    def over_allocated_people(self, week: str | None = None) -> dict[str, Any]:
        """People allocated above 100% of their week. Set week='next' when the user says next week, week='this' for
        this week, or a date like 2026-12-07; leave week empty only when no week is mentioned (all upcoming weeks)."""
        rs = self._board()
        w = parse_week(week, rs.as_of)
        start = w or resourcing.week_of(rs.as_of)
        r = resourcing.over_allocations(rs, from_week=start, to_week=w)
        return self._out({k: v for k, v in r.items() if k != "evidence"}, r["evidence"])

    def person_schedule(self, person: str, weeks_ahead: int = 4) -> dict[str, Any]:
        """A person's allocations (share of their week) by week and workstream, from this week forward. Pass the
        person's first name. Keep weeks_ahead at 4 unless the user asks for a different number of weeks."""
        rs = self._board()
        who = resourcing.match_person(rs, person)
        if who is None:
            raise ToolError(f"No one called '{person}' on the board. People: {', '.join(resourcing.people(rs))}.")
        r = resourcing.person_schedule(rs, who, weeks_ahead=max(1, min(weeks_ahead, 12)))
        return self._out({k: v for k, v in r.items() if k != "evidence"}, r["evidence"])

    def workstream_details(self, name: str) -> dict[str, Any]:
        """Team by role, outstanding work, upcoming milestones and notes for one workstream."""
        rs = self._board()
        ws = resourcing.find_workstream(rs, name)
        if ws is None:
            raise ToolError(f"No workstream '{name}'. Workstreams: {', '.join(w.name for w in rs.workstreams)}.")
        r = resourcing.workstream_summary(rs, ws)
        return self._out({k: v for k, v in r.items() if k != "evidence"}, r["evidence"])

    def outstanding_work(self, month: str | None = None) -> dict[str, Any]:
        """Outstanding bugs and stories per workstream, for one delivery month (e.g. 'Dec 2026') or all."""
        rs = self._board()
        r = resourcing.outstanding_work(rs, parse_month(month, rs.as_of))
        return self._out({k: v for k, v in r.items() if k != "evidence"}, r["evidence"])

    def upcoming_milestones(self, weeks_ahead: int = 4, week: str | None = None) -> dict[str, Any]:
        """Milestones on the board from this week forward; with week ('this', 'next' or a date) only that week."""
        rs = self._board()
        start = parse_week(week, rs.as_of)
        r = resourcing.upcoming_milestones(rs, weeks_ahead=1 if start else max(1, min(weeks_ahead, 12)), start=start)
        return self._out({k: v for k, v in r.items() if k != "evidence"}, r["evidence"])

    def _all_issues(self):
        return [(snap, i) for snap in self.ds.projects for i in snap.issues]

    def issue_details(self, key: str) -> dict[str, Any]:
        """One Jira issue by key (e.g. K41-3157): summary, type, status, assignee, epic, due date, blockers."""
        match = next(((s, i) for s, i in self._all_issues() if i.key == key.strip().upper()), None)
        if match is None:
            raise ToolError(f"No issue {key} in the data that was read.")
        snap, i = match
        return self._out({
            "key": i.key, "project": snap.project.key, "summary": i.summary, "type": i.raw_type,
            "status": i.status.name, "assignee": i.assignee.display_name if i.assignee else None,
            "epic": i.epic_key, "due_date": i.due_date, "overdue": metrics.is_overdue(i, snap),
            "blocked_by": [link.target_key for link in i.links if link.type == "is_blocked_by"],
        }, [{"label": i.key, "url": i.url}])

    def assigned_issues(self, person: str) -> dict[str, Any]:
        """Open Jira issues assigned to a person (first name is enough), most urgent first."""
        name = person.strip().lower().split()[0] if person.strip() else ""
        rows = [
            {"key": i.key, "summary": i.summary, "status": i.status.name, "due_date": i.due_date,
             "overdue": metrics.is_overdue(i, snap), "url": i.url, "assignee": i.assignee.display_name}
            for snap, i in self._all_issues()
            if name and i.assignee and i.assignee.display_name.lower().split()[0] == name and not metrics.is_done(i)
        ]
        rows.sort(key=lambda r: (not r["overdue"], r["due_date"] is None, r["due_date"] or "", r["key"]))
        return self._out({"person": rows[0]["assignee"] if rows else person, "issues": rows},
                         [{"label": r["key"], "url": r["url"]} for r in rows])

    def tools(self) -> list[Tool]:
        names = (["project_status", "delayed_epics", "overdue_issues", "blockers", "issue_workload", "issue_details",
                  "assigned_issues"] if self.ds.projects else [])
        if self.ds.resourcing:
            names += ["list_workstreams", "over_allocated_people", "person_schedule", "workstream_details",
                      "outstanding_work", "upcoming_milestones"]
        if "project_status" not in names:
            names.insert(0, "project_status")
        return [Tool(n, getattr(self, n).__doc__ or n, getattr(self, n)) for n in names]
