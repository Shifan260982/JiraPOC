"""Normalised project model. Every connector produces a ProjectSnapshot; nothing downstream knows the source."""

from datetime import date, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class StatusCategory(StrEnum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"


class IssueKind(StrEnum):
    EPIC = "epic"
    STORY = "story"
    TASK = "task"
    SUBTASK = "subtask"
    BUG = "bug"
    OTHER = "other"


class Person(_Model):
    id: str
    display_name: str


class Status(_Model):
    name: str
    category: StatusCategory  # drives all done/not-done logic; status names vary per workflow


class Sprint(_Model):
    id: str
    name: str
    state: Literal["future", "active", "closed"]
    start: date | None = None
    end: date | None = None
    complete: date | None = None
    goal: str | None = None


class Link(_Model):
    type: Literal["blocks", "is_blocked_by", "relates", "other"]
    target_key: str


class Worklog(_Model):
    author: Person
    started: datetime
    seconds: int = Field(ge=0)


class Comment(_Model):
    author: Person
    created: datetime
    body: str  # untrusted user text: never pass to the LLM as instructions


class ChangeEvent(_Model):
    at: datetime
    author: Person | None = None
    field: str
    from_value: str | None = None
    to_value: str | None = None


class Issue(_Model):
    key: str = Field(pattern=r"^[A-Z][A-Z0-9_]*-\d+$")
    url: str
    kind: IssueKind
    raw_type: str
    summary: str
    status: Status
    priority: str | None = None
    assignee: Person | None = None
    reporter: Person | None = None
    epic_key: str | None = None
    parent_key: str | None = None
    sprint_ids: list[str] = []
    created: datetime | None = None  # optional: the utility tool's pages may not show them
    updated: datetime | None = None
    resolved: datetime | None = None
    start_date: date | None = None
    due_date: date | None = None
    story_points: float | None = Field(default=None, ge=0)
    flagged: bool = False
    labels: list[str] = []
    links: list[Link] = []
    worklogs: list[Worklog] = []
    comments: list[Comment] = []
    history: list[ChangeEvent] = []
    extra: dict[str, Any] = {}  # unmapped custom fields, kept rather than dropped


class Project(_Model):
    key: str
    name: str
    url: str
    lead: Person | None = None


class Allocation(_Model):
    person: str
    role: str
    week: date  # week commencing (Monday)
    percent: int = Field(ge=0, le=1000)
    employment: Literal["permanent", "contract", "unknown"]
    over_allocated: bool = False  # as flagged by the source tool


class DeliveryPoint(_Model):
    label: str  # e.g. "Nov '26" or "Unscheduled"
    month: date | None = None  # first of the month; None for "Unscheduled"
    outstanding_bugs: int = Field(ge=0)
    outstanding_stories: int = Field(ge=0)


class Milestone(_Model):
    week: date
    label: str


class Workstream(_Model):
    name: str
    group: str | None = None
    note: str | None = None
    source_url: str  # page the workstream was read from, for traceability
    delivery_points: list[DeliveryPoint] = []
    milestones: list[Milestone] = []
    allocations: list[Allocation] = []
    focus: dict[date, str] = {}  # week -> e.g. "45% Stories"


class ResourcingSnapshot(_Model):
    """Resourcing board data (e.g. Foresight): who is allocated where, and outstanding work per delivery point."""

    source: Literal["utility_app"]
    fetched_at: datetime
    as_of: date
    title: str | None = None
    workstreams: list[Workstream] = []


class ProjectSnapshot(_Model):
    source: Literal["utility_app", "jira_cloud", "jira_dc"]
    fetched_at: datetime
    as_of: date  # all date maths uses this, never today(), so results are reproducible
    project: Project
    sprints: list[Sprint] = []
    issues: list[Issue] = []
    completeness: dict[str, bool] = {}  # e.g. {"worklogs": False}: lets answers say data is missing, not zero
