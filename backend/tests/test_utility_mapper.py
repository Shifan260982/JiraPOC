from datetime import date, datetime

from fastapi.testclient import TestClient

from app.analytics.metrics import project_overview
from app.connectors.utility_app.mapper import UtilityScan, map_scan, parse_datetime
from app.domain.schema import IssueKind, StatusCategory
from app.main import app

TOOL = "https://tool.example.com"


def cells(*values, href=None):
    row = [{"text": v} for v in values]
    if href:
        row[0]["href"] = href
    return row


def table(page, headers, rows, index=0):
    return {"page_url": f"{TOOL}/{page}", "page_title": page, "table_index": index, "pagination_step": 0,
            "headers": headers, "rows": rows}


SCAN = {
    "scanned_at": "2026-11-20T09:00:00Z",
    "date_order": "DMY",
    "tables": [
        table("epics", ["Key", "Summary", "Type", "Status", "Due date"], [
            cells("PRJ-1", "Checkout", "Epic", "In Progress", "15/11/2026", href="https://x.atlassian.net/browse/PRJ-1"),
            cells("PRJ-2", "Search", "Epic", "Done", ""),
        ]),
        table("issues", ["Issue", "Title", "Issue Type", "Status", "Assignee", "Epic", "Due", "Story Points", "Flagged", "Team"], [
            cells("PRJ-3", "Pay", "Story", "In Review", "Alice", "Checkout", "10/11/2026", "3", "", "Blue"),
            cells("PRJ-4", "Cart", "Task", "Closed", "Unassigned", "PRJ-1", "", "abc", "Yes", "Blue"),
            cells("OPS-1", "Outage", "Bug", "Waiting for vendor", "Bob", "-", "31/13/2026", "", "", ""),
        ]),
        table("dashboard", ["Status", "Count"], [cells("Done", "4")]),  # chart legend: no keys, ignored
        table("issues", ["Issue", "Title"], [cells("PRJ-3", "A different title")], index=1),  # duplicate: first wins
        table("other", [], [cells("PRJ-5", "Orphan"), cells("PRJ-6", "Another")]),  # no headers: key column detected
    ],
}


def mapped():
    snapshots, warnings, stats = map_scan(UtilityScan.model_validate(SCAN))
    return {s.project.key: s for s in snapshots}, warnings, stats


def issue(snaps, key):
    return next(i for s in snaps.values() for i in s.issues if i.key == key)


def test_stats_and_projects():
    snaps, _, stats = mapped()
    assert stats == {"tables_received": 5, "issue_tables": 4, "rows_received": 9, "issues": 7}
    assert sorted(snaps) == ["OPS", "PRJ"]
    prj = snaps["PRJ"]
    assert prj.source == "utility_app"
    assert prj.as_of == date(2026, 11, 20)
    assert prj.project.url == f"{TOOL}/epics"
    assert [i.key for i in prj.issues] == ["PRJ-1", "PRJ-2", "PRJ-3", "PRJ-4", "PRJ-5", "PRJ-6"]
    assert prj.completeness["flags"] is True and prj.completeness["links"] is False


def test_issue_fields_are_mapped_and_merged():
    snaps, _, _ = mapped()
    epic = issue(snaps, "PRJ-1")
    # The source is the page the row was read from, not the Jira link in the row.
    assert (epic.kind, epic.due_date, epic.url) == (IssueKind.EPIC, date(2026, 11, 15), f"{TOOL}/epics")

    story = issue(snaps, "PRJ-3")
    assert story.summary == "Pay"  # first sighting wins
    assert story.epic_key == "PRJ-1"  # resolved from the epic's name
    assert story.status.category is StatusCategory.IN_PROGRESS
    assert (story.due_date, story.story_points) == (date(2026, 11, 10), 3.0)
    assert story.assignee.display_name == "Alice"
    assert story.extra == {"Team": "Blue"}
    assert story.url == f"{TOOL}/issues"  # no Jira link in the row: falls back to the tool page

    task = issue(snaps, "PRJ-4")
    assert (task.epic_key, task.status.category, task.assignee, task.story_points, task.flagged) == (
        "PRJ-1", StatusCategory.DONE, None, None, True)


def test_unmappable_values_become_warnings_not_guesses():
    snaps, warnings, _ = mapped()
    bug = issue(snaps, "OPS-1")
    assert bug.status.category is StatusCategory.TODO
    assert bug.due_date is None
    assert "Status 'Waiting for vendor' not recognised; treated as To Do" in warnings
    assert "Unreadable date in 'due_date': '31/13/2026'" in warnings
    assert "Unreadable story points: 'abc'" in warnings
    assert "Columns kept as extra data (not mapped): Team" in warnings


def test_metrics_run_on_mapped_snapshot():
    snaps, _, _ = mapped()
    o = project_overview(snaps["PRJ"])
    assert o["epics_delayed"] == 1  # PRJ-1 past due and PRJ-3 overdue
    assert o["blocked_issues"] == 0  # PRJ-4 is flagged but done


def test_numeric_id_column_is_not_taken_as_key():
    scan = UtilityScan.model_validate({**SCAN, "tables": [
        table("t", ["ID", "Jira key", "Status"], [cells("101", "ABC-1", "Done"), cells("102", "ABC-2", "Open")]),
    ]})
    snaps, _, _ = map_scan(scan)
    assert [i.key for i in snaps[0].issues] == ["ABC-1", "ABC-2"]


def test_parse_datetime():
    assert parse_datetime("11/10/2026", "MDY") == datetime(2026, 11, 10)
    assert parse_datetime("11/10/2026", "DMY") == datetime(2026, 10, 11)
    assert parse_datetime("20/Nov/26", "DMY") == datetime(2026, 11, 20)
    assert parse_datetime("20/11/2026 14:30", "DMY") == datetime(2026, 11, 20)
    assert parse_datetime("2026-11-20", "MDY") == datetime(2026, 11, 20)
    assert parse_datetime("soon", "DMY") is None


def test_ingest_endpoint():
    client = TestClient(app)
    res = client.post("/api/v1/sources/utility/ingest", json=SCAN)
    assert res.status_code == 200
    body = res.json()
    assert [p["key"] for p in body["projects"]] == ["OPS", "PRJ"]
    assert body["projects"][1]["overview"]["epics_delayed"] == 1
    assert body["projects"][1]["snapshot"]["source"] == "utility_app"

    assert client.post("/api/v1/sources/utility/ingest", json={**SCAN, "date_order": "YMD"}).status_code == 422
