"""Maps tables scanned from the utility tool's pages into ProjectSnapshots.

The tool's page layout is unknown, so tables are recognised by their column headers (HEADER_SYNONYMS) and
issue keys. Rows for the same issue seen on several pages are merged. Anything that cannot be mapped
confidently is reported as a warning rather than guessed silently.
"""

import re
from collections import Counter, defaultdict
from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from app.domain.schema import Issue, IssueKind, Link, Person, Project, ProjectSnapshot, Status, StatusCategory

# ---- Request model (trust boundary: sizes are capped) ----

Text = Annotated[str, Field(max_length=5_000)]


class CellPart(BaseModel):
    text: Text
    cls: Annotated[str, Field(max_length=500)] = ""


class ScannedCell(BaseModel):
    text: Text
    href: Annotated[str, Field(max_length=2_000)] | None = None
    span: int = Field(default=1, ge=1, le=200)
    parts: list[CellPart] = Field(default=[], max_length=50)


class ScannedTable(BaseModel):
    page_url: Annotated[str, Field(max_length=2_000)]
    page_title: Text = ""
    table_index: int = Field(ge=0)
    pagination_step: int = Field(ge=0)
    headers: list[Text] = Field(max_length=200)
    header_spans: list[Annotated[int, Field(ge=1, le=200)]] = Field(default=[], max_length=200)
    context: list[CellPart] = Field(default=[], max_length=20)
    rows: list[Annotated[list[ScannedCell], Field(max_length=200)]] = Field(max_length=20_000)


class UtilityScan(BaseModel):
    scanned_at: datetime
    date_order: Literal["DMY", "MDY"] = "DMY"
    pages_visited: list[Annotated[str, Field(max_length=2_000)]] = Field(default=[], max_length=1_000)
    tables: list[ScannedTable] = Field(max_length=5_000)


# ---- Mapping rules ----

KEY_RE = re.compile(r"[A-Z][A-Z0-9_]*-\d+")
BROWSE_RE = re.compile(r"/browse/([A-Z][A-Z0-9_]*-\d+)")
EMPTY = {"", "-", "–", "—", "n/a", "na", "null", "unassigned", "not set"}
TRUTHY = {"yes", "y", "true", "1", "flagged", "impediment", "✓", "✔"}

HEADER_SYNONYMS: dict[str, set[str]] = {
    "key": {"key", "issuekey", "issue", "issueid", "id", "ticket", "ticketid", "jira", "jirakey", "jiraid"},
    "summary": {"summary", "title", "name", "issuesummary", "issuename"},
    "type": {"type", "issuetype", "kind"},
    "status": {"status", "state", "issuestatus"},
    "status_category": {"statuscategory", "category"},
    "priority": {"priority"},
    "assignee": {"assignee", "assignedto", "owner"},
    "reporter": {"reporter", "createdby"},
    "epic": {"epic", "epiclink", "epickey", "parentepic", "epicname"},
    "parent": {"parent", "parentkey", "parentissue"},
    "sprint": {"sprint", "sprints", "sprintname"},
    "due_date": {"duedate", "due", "targetdate", "deadline"},
    "start_date": {"startdate", "start"},
    "created": {"created", "createddate", "createdon"},
    "updated": {"updated", "lastupdated", "updateddate"},
    "resolved": {"resolved", "resolutiondate", "resolveddate", "completeddate"},
    "story_points": {"storypoints", "storypointestimate", "points", "sp"},
    "labels": {"labels", "label"},
    "flagged": {"flagged", "flag", "impediment"},
    "blocked_by": {"blockedby", "isblockedby", "blockers"},
    "project": {"project", "projectname"},
}
_FIELD_BY_HEADER = {syn: field for field, syns in HEADER_SYNONYMS.items() for syn in syns}

# D6: status name -> category when the tool shows no category column. Needs confirming against the client's workflows.
STATUS_CATEGORY_BY_NAME = {
    **dict.fromkeys(["done", "closed", "resolved", "complete", "completed", "released"], StatusCategory.DONE),
    **dict.fromkeys(["inprogress", "inreview", "review", "codereview", "testing", "intesting", "qa", "inqa",
                     "indevelopment", "development", "blocked"], StatusCategory.IN_PROGRESS),
    **dict.fromkeys(["todo", "open", "backlog", "new", "selectedfordevelopment", "reopened"], StatusCategory.TODO),
}
CATEGORY_COLUMN_VALUES = {
    "todo": StatusCategory.TODO, "new": StatusCategory.TODO,
    "inprogress": StatusCategory.IN_PROGRESS, "indeterminate": StatusCategory.IN_PROGRESS,
    "done": StatusCategory.DONE, "complete": StatusCategory.DONE,
}
KIND_BY_TYPE = {"epic": IssueKind.EPIC, "story": IssueKind.STORY, "userstory": IssueKind.STORY, "task": IssueKind.TASK,
                "subtask": IssueKind.SUBTASK, "bug": IssueKind.BUG, "defect": IssueKind.BUG}

DATE_FORMATS = {
    "DMY": ["%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y", "%d/%b/%y", "%d-%b-%Y", "%d %b %Y", "%d %B %Y", "%b %d, %Y", "%B %d, %Y"],
    "MDY": ["%m/%d/%Y", "%m-%d-%Y", "%m/%d/%y", "%d/%b/%y", "%d-%b-%Y", "%d %b %Y", "%d %B %Y", "%b %d, %Y", "%B %d, %Y"],
}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _value(text: str) -> str | None:
    t = text.strip()
    return None if t.lower() in EMPTY else t


def parse_datetime(text: str, order: Literal["DMY", "MDY"]) -> datetime | None:
    """Returns None for unparseable input. Time of day is kept for ISO values and dropped otherwise."""
    t = text.strip()
    try:
        return datetime.fromisoformat(t.replace("Z", "+00:00"))
    except ValueError:
        pass
    for candidate in (t, t.split(" ")[0]):  # second pass drops a trailing time such as "20/11/2026 14:30"
        for fmt in DATE_FORMATS[order]:
            try:
                return datetime.strptime(candidate, fmt)
            except ValueError:
                continue
    return None


def _column_map(table: ScannedTable) -> dict[int, str]:
    """Column index -> schema field. Falls back to detecting the key column by its values."""
    cols = {i: _FIELD_BY_HEADER[_norm(h)] for i, h in enumerate(table.headers) if _norm(h) in _FIELD_BY_HEADER}
    key_cols = [i for i, f in cols.items() if f == "key" and _mostly_keys(table, i)]
    for i in [i for i, f in cols.items() if f == "key" and i not in key_cols]:
        del cols[i]  # e.g. a numeric "ID" column
    if not key_cols:
        width = max((len(r) for r in table.rows), default=0)
        detected = next((i for i in range(width) if i not in cols and _mostly_keys(table, i)), None)
        if detected is not None:
            cols[detected] = "key"
    return cols


def _mostly_keys(table: ScannedTable, col: int) -> bool:
    values = [r[col].text.strip() for r in table.rows if col < len(r) and r[col].text.strip()]
    return bool(values) and sum(bool(KEY_RE.fullmatch(v)) for v in values) / len(values) >= 0.8


def _issue_url(key: str, row: list[ScannedCell], page_url: str) -> str:
    """Prefer a link to the issue itself (Jira /browse/KEY), else the tool page the row was read from."""
    for cell in row:
        if cell.href and (m := BROWSE_RE.search(cell.href)) and m.group(1) == key:
            return cell.href
    return page_url


class _Warnings:
    def __init__(self) -> None:
        self.counts: Counter[str] = Counter()

    def add(self, message: str) -> None:
        self.counts[message] += 1

    def as_list(self) -> list[str]:
        return [f"{m} ({n}×)" if n > 1 else m for m, n in sorted(self.counts.items())]


def map_scan(scan: UtilityScan) -> tuple[list[ProjectSnapshot], list[str], dict[str, int]]:
    warnings = _Warnings()
    records: dict[str, dict[str, Any]] = {}  # issue key -> merged raw fields; first non-empty value wins
    seen_fields: set[str] = set()
    issue_tables = 0

    for table in scan.tables:
        cols = _column_map(table)
        key_col = next((i for i, f in cols.items() if f == "key"), None)
        if key_col is None:
            continue
        issue_tables += 1
        seen_fields.update(cols.values())
        unmapped = [h for i, h in enumerate(table.headers) if i not in cols and h.strip()]
        for row in table.rows:
            if key_col >= len(row) or not KEY_RE.fullmatch(key := row[key_col].text.strip()):
                continue
            rec = records.setdefault(key, {"_page_url": table.page_url})
            rec.setdefault("_url", _issue_url(key, row, table.page_url))
            for i, field in cols.items():
                if i < len(row) and (v := _value(row[i].text)) is not None:
                    rec.setdefault(field, v)
            for i, header in enumerate(table.headers):
                if i not in cols and i < len(row) and header.strip() and (v := _value(row[i].text)) is not None:
                    rec.setdefault("_extra", {}).setdefault(header.strip(), v)
        if unmapped:
            warnings.add(f"Columns kept as extra data (not mapped): {', '.join(sorted(set(unmapped)))}")

    # Callers decide whether "no issue tables" matters (a resourcing board alone has none).
    if records and "type" not in seen_fields:
        warnings.add("No issue type column found: epics cannot be identified.")
    if records and "status" not in seen_fields:
        warnings.add("No status column found: progress cannot be calculated.")

    issues = [_to_issue(key, rec, scan.date_order, warnings) for key, rec in records.items()]
    issues = _resolve_epics(issues, warnings)

    by_project: dict[str, list[Issue]] = defaultdict(list)
    for issue in issues:
        by_project[issue.key.rsplit("-", 1)[0]].append(issue)

    completeness = {"flags": "flagged" in seen_fields, "sprints": False, "links": "blocked_by" in seen_fields,
                    "worklogs": False, "comments": False, "history": False}
    snapshots = [
        ProjectSnapshot(
            source="utility_app",
            fetched_at=scan.scanned_at,
            as_of=scan.scanned_at.date(),
            project=Project(
                key=pkey,
                name=next((records[i.key]["project"] for i in project_issues if "project" in records[i.key]), pkey),
                url=records[project_issues[0].key]["_page_url"],
            ),
            issues=sorted(project_issues, key=lambda i: (len(i.key), i.key)),
            completeness=completeness,
        )
        for pkey, project_issues in sorted(by_project.items())
    ]
    stats = {
        "tables_received": len(scan.tables),
        "issue_tables": issue_tables,
        "rows_received": sum(len(t.rows) for t in scan.tables),
        "issues": len(issues),
    }
    return snapshots, warnings.as_list(), stats


def _to_issue(key: str, rec: dict[str, Any], order: Literal["DMY", "MDY"], warnings: _Warnings) -> Issue:
    def when(field: str) -> datetime | None:
        if field not in rec:
            return None
        parsed = parse_datetime(rec[field], order)
        if parsed is None:
            warnings.add(f"Unreadable date in '{field}': {rec[field]!r}")
        return parsed

    def day(field: str) -> date | None:
        parsed = when(field)
        return parsed.date() if parsed else None

    status_name = rec.get("status", "Unknown")
    category = CATEGORY_COLUMN_VALUES.get(_norm(rec.get("status_category", ""))) or STATUS_CATEGORY_BY_NAME.get(_norm(status_name))
    if category is None:
        warnings.add(f"Status '{status_name}' not recognised; treated as To Do")
        category = StatusCategory.TODO

    raw_type = rec.get("type", "Unknown")
    points = None
    if "story_points" in rec:
        try:
            points = float(rec["story_points"])
            if points < 0:
                raise ValueError
        except ValueError:
            warnings.add(f"Unreadable story points: {rec['story_points']!r}")
            points = None

    def person(field: str) -> Person | None:
        # The tool shows display names only, so the name doubles as the id.
        return Person(id=rec[field], display_name=rec[field]) if field in rec else None

    epic, parent = rec.get("epic"), rec.get("parent")
    extra = dict(rec.get("_extra", {}))
    if epic and not KEY_RE.fullmatch(epic):
        extra["_epic_name"] = epic  # resolved against epic summaries in _resolve_epics

    return Issue(
        key=key,
        url=rec["_url"],
        kind=KIND_BY_TYPE.get(_norm(raw_type), IssueKind.OTHER),
        raw_type=raw_type,
        summary=rec.get("summary", ""),
        status=Status(name=status_name, category=category),
        priority=rec.get("priority"),
        assignee=person("assignee"),
        reporter=person("reporter"),
        epic_key=epic if epic and KEY_RE.fullmatch(epic) else None,
        parent_key=parent if parent and KEY_RE.fullmatch(parent) else None,
        sprint_ids=[s.strip() for s in rec["sprint"].split(",") if s.strip()] if "sprint" in rec else [],
        created=when("created"),
        updated=when("updated"),
        resolved=when("resolved"),
        start_date=day("start_date"),
        due_date=day("due_date"),
        story_points=points,
        flagged=rec.get("flagged", "").strip().lower() in TRUTHY,
        labels=[s.strip() for s in rec["labels"].split(",") if s.strip()] if "labels" in rec else [],
        links=[Link(type="is_blocked_by", target_key=k) for k in KEY_RE.findall(rec.get("blocked_by", ""))],
        extra=extra,
    )


def _resolve_epics(issues: list[Issue], warnings: _Warnings) -> list[Issue]:
    """Fill epic_key from an epic name column, or from a parent that is an epic (Jira's newer hierarchy)."""
    epics_by_name = {i.summary.strip().lower(): i.key for i in issues if i.kind is IssueKind.EPIC and i.summary}
    epic_keys = {i.key for i in issues if i.kind is IssueKind.EPIC}
    resolved = []
    for issue in issues:
        epic_key = issue.epic_key
        extra = issue.extra
        if epic_key is None and (name := extra.get("_epic_name")):
            epic_key = epics_by_name.get(name.strip().lower())
            if epic_key is None:
                warnings.add(f"Epic '{name}' not found among scanned epics")
            extra = {k: v for k, v in extra.items() if k != "_epic_name"}
        if epic_key is None and issue.parent_key in epic_keys:
            epic_key = issue.parent_key
        resolved.append(issue.model_copy(update={"epic_key": epic_key, "extra": extra}))
    return resolved
