"""Parses Foresight resourcing-board tables (as scanned by the extension) into a ResourcingSnapshot.

Board layout per workstream (one table each):
  header: Delivery Point | <month columns, colspan = weeks shown> | Unscheduled
  Outstanding        "N bugs" / "N stories" per month
  W/C                week-commencing date per week column ("—" for months without weeks)
  Tasks / Milestones milestone chips per week
  <role rows>        allocation chips "First L. NN%" with classes fs-emp-<type> and "over"
  % Focus            e.g. "45% Stories" per week
The workstream name, note and group come from the headings in scope of the table (ScannedTable.context).
"""

import re
from datetime import date, datetime

from app.connectors.utility_app.mapper import CellPart, ScannedCell, ScannedTable, UtilityScan
from app.domain.schema import Allocation, DeliveryPoint, Milestone, ResourcingSnapshot, Workstream

MONTHS = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
MONTH_RE = re.compile(r"^([A-Za-z]{3})\w*\s*['’]?(\d{2}|\d{4})$")
CHIP_RE = re.compile(r"^(.+?)\s+(\d{1,4})%$")
BUGS_RE = re.compile(r"(\d+)\s+bugs?\b", re.I)
STORIES_RE = re.compile(r"(\d+)\s+stor(?:y|ies)\b", re.I)
NON_ROLE_ROWS = {"outstanding", "w/c", "tasks / milestones", "% focus"}


def is_foresight_table(table: ScannedTable) -> bool:
    labels = {r[0].text.strip().lower() for r in table.rows if r}
    return bool(table.headers) and table.headers[0].strip().lower() == "delivery point" and "w/c" in labels


def parse_month(label: str) -> date | None:
    m = MONTH_RE.match(label.strip())
    if not m or m.group(1).lower() not in MONTHS:
        return None
    year = int(m.group(2))
    return date(year + 2000 if year < 100 else year, MONTHS[m.group(1).lower()], 1)


def _expand(cells: list[ScannedCell]) -> list[tuple[ScannedCell, bool]]:
    """One entry per grid column: (cell, is_first_column_of_cell)."""
    return [(c, i == 0) for c in cells for i in range(c.span)]


def _context(table: ScannedTable, hint: str) -> str | None:
    return next((c.text for c in reversed(table.context) if hint in c.cls), None)


def _parse_table(table: ScannedTable, warnings: list[str]) -> Workstream:
    spans = table.header_spans or [1] * len(table.headers)
    month_cols: list[str] = [label for label, span in zip(table.headers[1:], spans[1:]) for _ in range(span)]
    rows = {r[0].text.strip().lower(): (r[0].text.strip(), _expand(r[1:])) for r in table.rows if r}
    name = _context(table, "ws-hdr") or next((c.text for c in reversed(table.context) if "note" not in c.cls), None)
    if not name:
        name = f"Workstream {table.table_index + 1}"
        warnings.append(f"A board table on {table.page_url} had no workstream title; named '{name}'")

    weeks: list[date | None] = []
    for cell, _ in rows.get("w/c", ("", []))[1]:
        try:
            weeks.append(datetime.strptime(cell.text.strip(), "%d/%m/%Y").date())
        except ValueError:
            weeks.append(None)

    delivery_points = []
    for col, (cell, first) in enumerate(rows.get("outstanding", ("", []))[1]):
        if not first or col >= len(month_cols):
            continue
        text = " ".join(p.text for p in cell.parts) or cell.text
        bugs, stories = BUGS_RE.search(text), STORIES_RE.search(text)
        delivery_points.append(DeliveryPoint(
            label=month_cols[col], month=parse_month(month_cols[col]),
            outstanding_bugs=int(bugs.group(1)) if bugs else 0,
            outstanding_stories=int(stories.group(1)) if stories else 0,
        ))

    def per_week(row_key: str):
        for col, (cell, _) in enumerate(rows.get(row_key, ("", []))[1]):
            if col < len(weeks) and weeks[col] is not None:
                yield weeks[col], cell

    milestones = [Milestone(week=w, label=p.text) for w, cell in per_week("tasks / milestones") for p in cell.parts]
    focus = {w: cell.text for w, cell in per_week("% focus") if cell.text and cell.text != "—"}

    allocations = []
    for key, (role, _) in rows.items():
        if key in NON_ROLE_ROWS:
            continue
        for w, cell in per_week(key):
            # A plain-text cell (no chips) still counts if it reads like an allocation.
            chips = cell.parts or ([CellPart(text=cell.text)] if cell.text and cell.text != "—" else [])
            for part in chips:
                m = CHIP_RE.match(part.text.strip())
                if not m:
                    warnings.append(f"Unreadable allocation '{part.text}' in {name} / {role}")
                    continue
                emp = re.search(r"fs-emp-(permanent|contract|unknown)", part.cls)
                allocations.append(Allocation(
                    person=m.group(1), role=role, week=w, percent=int(m.group(2)),
                    employment=emp.group(1) if emp else "unknown", over_allocated="over" in part.cls.split(),
                ))
    return Workstream(
        name=name, group=_context(table, "group"), note=_context(table, "note"), source_url=table.page_url,
        delivery_points=delivery_points, milestones=milestones, allocations=allocations, focus=focus,
    )


def map_foresight(scan: UtilityScan) -> tuple[ResourcingSnapshot | None, list[str]]:
    tables = [t for t in scan.tables if is_foresight_table(t)]
    if not tables:
        return None, []
    warnings: list[str] = []
    workstreams: dict[str, Workstream] = {}
    for t in tables:
        ws = _parse_table(t, warnings)
        workstreams.setdefault(ws.name, ws)  # same board read twice (e.g. two pages): keep the first
    title = next((c.text for c in tables[0].context if c.cls == ""), None) or tables[0].page_title or None
    return ResourcingSnapshot(
        source="utility_app", fetched_at=scan.scanned_at, as_of=scan.scanned_at.date(), title=title,
        workstreams=list(workstreams.values()),
    ), sorted(set(warnings))
