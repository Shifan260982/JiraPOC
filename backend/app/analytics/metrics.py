"""Deterministic project metrics over a ProjectSnapshot.

Every figure the assistant or a report shows comes from here, never from the LLM.
Business definitions follow docs/ARCHITECTURE.md §4.4 (pending client sign-off, D6).
Each result carries `evidence` (issue key + URL) so answers can cite their source.
"""

from collections import Counter, defaultdict
from datetime import timedelta
from typing import Any

from app.domain.schema import Issue, IssueKind, ProjectSnapshot, Sprint, StatusCategory

# D6: use story points for % complete only when this share of issues is estimated. Threshold to confirm.
STORY_POINT_COVERAGE = 0.8


def is_done(issue: Issue) -> bool:
    return issue.status.category is StatusCategory.DONE


def is_overdue(issue: Issue, snap: ProjectSnapshot) -> bool:
    return issue.due_date is not None and issue.due_date < snap.as_of and not is_done(issue)


def _ref(issue: Issue) -> dict[str, str]:
    return {"key": issue.key, "url": issue.url}


def _work_items(snap: ProjectSnapshot) -> list[Issue]:
    """Issues that count towards progress: no epics (containers) and no subtasks (would double-count parents)."""
    return [i for i in snap.issues if i.kind not in (IssueKind.EPIC, IssueKind.SUBTASK)]


def _non_epics(snap: ProjectSnapshot) -> list[Issue]:
    return [i for i in snap.issues if i.kind is not IssueKind.EPIC]


def percent_complete(issues: list[Issue]) -> tuple[float | None, str]:
    """Returns (percent rounded to 1 dp, basis). None when there is nothing to measure."""
    if not issues:
        return None, "none"
    estimated = [i for i in issues if i.story_points is not None]
    total_points = sum(i.story_points for i in estimated)
    if len(estimated) / len(issues) >= STORY_POINT_COVERAGE and total_points > 0:
        done_points = sum(i.story_points for i in estimated if is_done(i))
        return round(100 * done_points / total_points, 1), "story_points"
    return round(100 * sum(is_done(i) for i in issues) / len(issues), 1), "issue_count"


def project_overview(snap: ProjectSnapshot) -> dict[str, Any]:
    items = _work_items(snap)
    epics = [i for i in snap.issues if i.kind is IssueKind.EPIC]
    pct, basis = percent_complete(items)
    counts = Counter(i.status.category.value for i in items)
    return {
        "project": snap.project.key,
        "as_of": snap.as_of,
        "source": snap.source,
        "total_issues": len(items),
        "by_status": {c.value: counts.get(c.value, 0) for c in StatusCategory},
        "percent_complete": pct,
        "percent_basis": basis,
        "epics_total": len(epics),
        "epics_done": sum(is_done(e) for e in epics),
        "epics_delayed": len(epic_progress(snap, only_delayed=True)["epics"]),
        "overdue_issues": len(overdue_issues(snap)["issues"]),
        "blocked_issues": len(blockers(snap)["issues"]),
        "active_sprints": [s.name for s in snap.sprints if s.state == "active"],
        "missing_data": sorted(k for k, ok in snap.completeness.items() if not ok),
    }


def epic_progress(snap: ProjectSnapshot, only_delayed: bool = False) -> dict[str, Any]:
    children: dict[str, list[Issue]] = defaultdict(list)
    for i in _work_items(snap):
        if i.epic_key:
            children[i.epic_key].append(i)

    epics = []
    for epic in (i for i in snap.issues if i.kind is IssueKind.EPIC):
        kids = children[epic.key]
        overdue_kids = [k for k in kids if is_overdue(k, snap)]
        reasons = []
        if not is_done(epic):
            if epic.due_date is not None and epic.due_date < snap.as_of:
                reasons.append("epic_due_date_passed")
            if overdue_kids:
                reasons.append("overdue_child_issues")
        if only_delayed and not reasons:
            continue
        pct, basis = percent_complete(kids)
        epics.append({
            **_ref(epic),
            "summary": epic.summary,
            "status": epic.status.name,
            "due_date": epic.due_date,
            "children_total": len(kids),
            "children_done": sum(is_done(k) for k in kids),
            "percent_complete": pct,
            "percent_basis": basis,
            "delayed": bool(reasons),
            "delay_reasons": reasons,
            "overdue_children": [_ref(k) for k in overdue_kids],
        })
    return {"as_of": snap.as_of, "epics": epics, "evidence": [{"key": e["key"], "url": e["url"]} for e in epics]}


def overdue_issues(snap: ProjectSnapshot, assignee_id: str | None = None) -> dict[str, Any]:
    rows = [
        {
            **_ref(i),
            "summary": i.summary,
            "status": i.status.name,
            "assignee": i.assignee.display_name if i.assignee else None,
            "due_date": i.due_date,
            "days_overdue": (snap.as_of - i.due_date).days,
        }
        for i in _non_epics(snap)
        if is_overdue(i, snap) and (assignee_id is None or (i.assignee and i.assignee.id == assignee_id))
    ]
    rows.sort(key=lambda r: (-r["days_overdue"], r["key"]))
    return {"as_of": snap.as_of, "issues": rows, "evidence": [{"key": r["key"], "url": r["url"]} for r in rows]}


def blockers(snap: ProjectSnapshot) -> dict[str, Any]:
    """An open issue is blocked if flagged, or blocked by an issue that is not done (or not in this snapshot)."""
    by_key = {i.key: i for i in snap.issues}
    blocked_by: dict[str, set[str]] = defaultdict(set)
    # Read both link directions: a source may only record one side of the relationship.
    for i in snap.issues:
        for link in i.links:
            if link.type == "is_blocked_by":
                blocked_by[i.key].add(link.target_key)
            elif link.type == "blocks":
                blocked_by[link.target_key].add(i.key)

    rows = []
    for i in snap.issues:
        if is_done(i):
            continue
        open_blockers = sorted(
            k for k in blocked_by.get(i.key, ()) if k not in by_key or not is_done(by_key[k])
        )
        reasons = (["flagged"] if i.flagged else []) + (["blocked_by_issue"] if open_blockers else [])
        if not reasons:
            continue
        rows.append({
            **_ref(i),
            "summary": i.summary,
            "status": i.status.name,
            "assignee": i.assignee.display_name if i.assignee else None,
            "reasons": reasons,
            "blocked_by": [
                {"key": k, "url": by_key[k].url if k in by_key else None,
                 "status": by_key[k].status.name if k in by_key else None}
                for k in open_blockers
            ],
        })
    evidence = [{"key": r["key"], "url": r["url"]} for r in rows]
    evidence += [{"key": b["key"], "url": b["url"]} for r in rows for b in r["blocked_by"]]
    return {"as_of": snap.as_of, "issues": rows, "evidence": evidence}


def _find_sprint(snap: ProjectSnapshot, sprint_id: str | None) -> Sprint:
    if sprint_id is not None:
        for s in snap.sprints:
            if s.id == sprint_id:
                return s
        raise ValueError(f"Sprint '{sprint_id}' not found in project {snap.project.key}")
    closed = [s for s in snap.sprints if s.state == "closed" and (s.complete or s.end)]
    if not closed:
        raise ValueError(f"Project {snap.project.key} has no closed sprints")
    return max(closed, key=lambda s: s.complete or s.end)


def sprint_summary(snap: ProjectSnapshot, sprint_id: str | None = None) -> dict[str, Any]:
    """Defaults to the most recently closed sprint.

    shortcut: scope is the sprint's issues at fetch time, not at sprint start (needs history); upgrade when
    changelogs are fetched.
    """
    sprint = _find_sprint(snap, sprint_id)
    items = [i for i in _work_items(snap) if sprint.id in i.sprint_ids]
    cutoff = sprint.complete or sprint.end
    completed = [
        i for i in items
        if is_done(i) and (sprint.state != "closed" or (i.resolved is not None and i.resolved.date() <= cutoff))
    ]
    completed_keys = {i.key for i in completed}
    not_completed = [i for i in items if i.key not in completed_keys]

    def points(issues: list[Issue]) -> float:
        return sum(i.story_points or 0 for i in issues)

    return {
        "sprint_id": sprint.id,
        "name": sprint.name,
        "state": sprint.state,
        "start": sprint.start,
        "end": sprint.end,
        "complete": sprint.complete,
        "goal": sprint.goal,
        "issues_total": len(items),
        "issues_completed": len(completed),
        "issues_not_completed": len(not_completed),
        "completion_percent": round(100 * len(completed) / len(items), 1) if items else None,
        "points_total": points(items),
        "points_completed": points(completed),
        "completed": [_ref(i) for i in completed],
        "not_completed": [_ref(i) for i in not_completed],
        "evidence": [_ref(i) for i in items],
    }


def compare_sprints(snap: ProjectSnapshot, sprint_a: str, sprint_b: str) -> dict[str, Any]:
    a, b = sprint_summary(snap, sprint_a), sprint_summary(snap, sprint_b)
    delta_pct = (
        round(b["completion_percent"] - a["completion_percent"], 1)
        if a["completion_percent"] is not None and b["completion_percent"] is not None else None
    )
    return {
        "a": a,
        "b": b,
        "delta": {
            "issues_completed": b["issues_completed"] - a["issues_completed"],
            "points_completed": b["points_completed"] - a["points_completed"],
            "completion_percent": delta_pct,
        },
        "evidence": a["evidence"] + b["evidence"],
    }


def workload(snap: ProjectSnapshot) -> dict[str, Any]:
    groups: dict[str, list[Issue]] = defaultdict(list)
    for i in _non_epics(snap):
        if not is_done(i):
            groups[i.assignee.display_name if i.assignee else "Unassigned"].append(i)
    people = [
        {
            "assignee": name,
            "open": len(issues),
            "in_progress": sum(i.status.category is StatusCategory.IN_PROGRESS for i in issues),
            "overdue": sum(is_overdue(i, snap) for i in issues),
            "issues": [_ref(i) for i in issues],
        }
        for name, issues in groups.items()
    ]
    people.sort(key=lambda p: (-p["open"], p["assignee"]))
    return {"as_of": snap.as_of, "people": people, "evidence": [r for p in people for r in p["issues"]]}


def upcoming_deadlines(snap: ProjectSnapshot, days: int = 14) -> dict[str, Any]:
    if days < 0:
        raise ValueError("days must be non-negative")
    horizon = snap.as_of + timedelta(days=days)
    rows = sorted(
        (
            {**_ref(i), "summary": i.summary, "kind": i.kind.value, "status": i.status.name,
             "assignee": i.assignee.display_name if i.assignee else None, "due_date": i.due_date}
            for i in snap.issues
            if not is_done(i) and i.due_date is not None and snap.as_of <= i.due_date <= horizon
        ),
        key=lambda r: (r["due_date"], r["key"]),
    )
    return {"as_of": snap.as_of, "until": horizon, "issues": rows,
            "evidence": [{"key": r["key"], "url": r["url"]} for r in rows]}
