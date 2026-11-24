import pytest

from app.analytics import metrics as m
from app.domain.schema import IssueKind, Link
from tests.conftest import DONE, TODO, issue


def keys(rows):
    return [r["key"] for r in rows]


def test_project_overview(snap):
    o = m.project_overview(snap)
    assert o["total_issues"] == 8  # epics and subtasks excluded
    assert o["by_status"] == {"todo": 3, "in_progress": 2, "done": 3}
    assert (o["percent_complete"], o["percent_basis"]) == (37.5, "issue_count")  # only 50% estimated
    assert (o["epics_total"], o["epics_done"], o["epics_delayed"]) == (3, 1, 1)
    assert (o["overdue_issues"], o["blocked_issues"]) == (2, 3)
    assert o["active_sprints"] == ["Sprint 12"]
    assert o["missing_data"] == ["worklogs"]


def test_epic_progress_flags_only_open_epics_past_due_or_with_overdue_children(snap):
    epics = {e["key"]: e for e in m.epic_progress(snap)["epics"]}
    assert epics["PRJ-1"]["delayed"] is False
    # both children estimated, so points (3 of 8) are used, not issue count (1 of 2)
    assert (epics["PRJ-1"]["percent_complete"], epics["PRJ-1"]["percent_basis"]) == (37.5, "story_points")
    assert epics["PRJ-4"]["delay_reasons"] == ["epic_due_date_passed", "overdue_child_issues"]
    assert keys(epics["PRJ-4"]["overdue_children"]) == ["PRJ-5"]
    assert epics["PRJ-7"]["delayed"] is False  # done, so a past due date is not a delay
    assert epics["PRJ-7"]["percent_complete"] is None  # no children: unknown, not 0%

    delayed = m.epic_progress(snap, only_delayed=True)
    assert keys(delayed["epics"]) == ["PRJ-4"]
    assert keys(delayed["evidence"]) == ["PRJ-4"]


def test_overdue_includes_subtasks_sorted_by_days_overdue(snap):
    r = m.overdue_issues(snap)
    assert keys(r["issues"]) == ["PRJ-10", "PRJ-5"]
    assert [i["days_overdue"] for i in r["issues"]] == [19, 10]
    assert keys(m.overdue_issues(snap, assignee_id="u2")["issues"]) == ["PRJ-5"]


def test_blockers_reads_both_link_directions_and_flags(snap):
    rows = {r["key"]: r for r in m.blockers(snap)["issues"]}
    assert set(rows) == {"PRJ-5", "PRJ-8", "PRJ-9"}
    assert rows["PRJ-5"]["reasons"] == ["blocked_by_issue"]
    assert rows["PRJ-8"]["reasons"] == ["flagged"]
    assert keys(rows["PRJ-9"]["blocked_by"]) == ["PRJ-8"]  # only PRJ-8 recorded the "blocks" side


def test_blocker_resolved_or_external(snap):
    s = snap.model_copy(update={"issues": [
        issue("PRJ-1", links=[Link(type="is_blocked_by", target_key="PRJ-2")]),
        issue("PRJ-2", status=DONE),
        issue("PRJ-3", links=[Link(type="is_blocked_by", target_key="OTHER-9")]),
    ]})
    rows = m.blockers(s)["issues"]
    assert keys(rows) == ["PRJ-3"]  # done blocker clears; unknown external blocker still counts
    assert rows[0]["blocked_by"] == [{"key": "OTHER-9", "url": None, "status": None}]


def test_sprint_summary_defaults_to_last_closed_and_uses_resolution_date(snap):
    s = m.sprint_summary(snap)
    assert s["name"] == "Sprint 11"
    assert (s["issues_total"], s["issues_completed"]) == (5, 1)  # PRJ-11 resolved after sprint end
    assert keys(s["completed"]) == ["PRJ-12"]
    assert (s["completion_percent"], s["points_total"], s["points_completed"]) == (20.0, 15, 8)


def test_compare_sprints(snap):
    c = m.compare_sprints(snap, "10", "11")
    assert c["a"]["completion_percent"] == 100.0
    assert c["delta"] == {"issues_completed": 0, "points_completed": 5, "completion_percent": -80.0}


def test_sprint_errors(snap):
    with pytest.raises(ValueError, match="not found"):
        m.sprint_summary(snap, "999")
    with pytest.raises(ValueError, match="no closed sprints"):
        m.sprint_summary(snap.model_copy(update={"sprints": []}))


def test_workload(snap):
    people = m.workload(snap)["people"]
    assert [(p["assignee"], p["open"], p["in_progress"], p["overdue"]) for p in people] == [
        ("Alice", 3, 2, 1), ("Bob", 2, 0, 1), ("Unassigned", 1, 0, 0),
    ]


def test_upcoming_deadlines(snap):
    assert keys(m.upcoming_deadlines(snap, days=14)["issues"]) == ["PRJ-3"]
    assert keys(m.upcoming_deadlines(snap, days=60)["issues"]) == ["PRJ-3", "PRJ-1"]
    with pytest.raises(ValueError):
        m.upcoming_deadlines(snap, days=-1)


def test_percent_complete_uses_story_points_when_mostly_estimated():
    issues = [issue(f"P-{n}", status=DONE if n == 1 else TODO, story_points=pts) for n, pts in
              [(1, 8), (2, 2), (3, 0), (4, 0), (5, None)]]  # 80% estimated
    assert m.percent_complete(issues) == (80.0, "story_points")
    assert m.percent_complete([]) == (None, "none")
    assert m.percent_complete([issue("P-1", status=DONE, story_points=0)]) == (100.0, "issue_count")


def test_schema_rejects_bad_issue_key():
    with pytest.raises(ValueError):
        issue("not-a-key", IssueKind.TASK)
