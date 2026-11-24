import os
from datetime import date, datetime

import pytest

# Tests must never call a real model API, even when the developer's .env holds a key.
os.environ["LLM_PROVIDER"] = "none"

from app.domain.schema import (
    Issue, IssueKind, Link, Person, Project, ProjectSnapshot, Sprint, Status, StatusCategory,
)

AS_OF = date(2026, 11, 20)
ALICE = Person(id="u1", display_name="Alice")
BOB = Person(id="u2", display_name="Bob")
TODO = Status(name="To Do", category=StatusCategory.TODO)
DOING = Status(name="In Progress", category=StatusCategory.IN_PROGRESS)
DONE = Status(name="Done", category=StatusCategory.DONE)


def issue(key: str, kind: IssueKind = IssueKind.STORY, status: Status = TODO, **kw) -> Issue:
    return Issue(
        key=key, url=f"https://example.atlassian.net/browse/{key}", kind=kind, raw_type=kind.value.title(),
        summary=f"Summary of {key}", status=status, created=datetime(2026, 9, 1), updated=datetime(2026, 11, 1),
        **kw,
    )


@pytest.fixture
def snap() -> ProjectSnapshot:
    """Small project covering on-track, delayed, blocked, overdue and sprint cases."""
    return ProjectSnapshot(
        source="jira_cloud",
        fetched_at=datetime(2026, 11, 20, 9, 0),
        as_of=AS_OF,
        project=Project(key="PRJ", name="Project", url="https://example.atlassian.net/browse/PRJ"),
        sprints=[
            Sprint(id="10", name="Sprint 10", state="closed",
                   start=date(2026, 10, 20), end=date(2026, 11, 2), complete=date(2026, 11, 2)),
            Sprint(id="11", name="Sprint 11", state="closed",
                   start=date(2026, 11, 3), end=date(2026, 11, 16), complete=date(2026, 11, 16)),
            Sprint(id="12", name="Sprint 12", state="active", start=date(2026, 11, 17), end=date(2026, 11, 30)),
        ],
        issues=[
            # Epic 1: on track (no due date passed, no overdue children)
            issue("PRJ-1", IssueKind.EPIC, DOING, due_date=date(2026, 12, 31)),
            issue("PRJ-2", epic_key="PRJ-1", status=DONE, story_points=3, sprint_ids=["10"],
                  resolved=datetime(2026, 10, 30), assignee=ALICE),
            issue("PRJ-3", epic_key="PRJ-1", status=DOING, story_points=5, sprint_ids=["11", "12"], assignee=ALICE,
                  due_date=date(2026, 11, 25)),
            # Epic 2: delayed by its own due date and by an overdue child
            issue("PRJ-4", IssueKind.EPIC, DOING, due_date=date(2026, 11, 15)),
            issue("PRJ-5", epic_key="PRJ-4", status=TODO, assignee=BOB, due_date=date(2026, 11, 10),
                  links=[Link(type="is_blocked_by", target_key="PRJ-6")]),
            issue("PRJ-6", IssueKind.TASK, epic_key="PRJ-4", status=DOING, assignee=ALICE, sprint_ids=["11"]),
            # Done epic with a past due date: not delayed
            issue("PRJ-7", IssueKind.EPIC, DONE, due_date=date(2026, 10, 1), resolved=datetime(2026, 9, 30)),
            # Unassigned flagged bug, blocks PRJ-9 (only the "blocks" side recorded)
            issue("PRJ-8", IssueKind.BUG, TODO, flagged=True, links=[Link(type="blocks", target_key="PRJ-9")],
                  sprint_ids=["11"], resolved=None),
            issue("PRJ-9", status=TODO, assignee=BOB),
            # Subtask: counted for overdue/workload, not for progress
            issue("PRJ-10", IssueKind.SUBTASK, TODO, parent_key="PRJ-3", assignee=ALICE, due_date=date(2026, 11, 1)),
            # Done in sprint 11 but resolved after sprint end: not completed in sprint 11
            issue("PRJ-11", status=DONE, sprint_ids=["11"], resolved=datetime(2026, 11, 18), story_points=2),
            issue("PRJ-12", status=DONE, sprint_ids=["11"], resolved=datetime(2026, 11, 14), story_points=8),
        ],
        completeness={"worklogs": False, "comments": True},
    )
