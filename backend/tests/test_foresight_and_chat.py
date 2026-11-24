"""End to end on synthetic data: extension scan of the mock Foresight tool -> ingest -> chat.

The fixture is produced by the real page reader (extension: npm run fixture) over samples/mock-tool.
"""

import json
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from app import store
from app.agent import demo, llm
from app.agent.tools import Toolset, parse_month
from app.connectors.utility_app.foresight import map_foresight, parse_month as board_month
from app.connectors.utility_app.mapper import UtilityScan, map_scan
from app.main import app

SCAN = json.loads((Path(__file__).parent / "fixtures" / "sample_scan.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def dataset():
    scan = UtilityScan.model_validate(SCAN)
    projects, _, _ = map_scan(scan)
    board, warnings = map_foresight(scan)
    assert warnings == []
    return store.put(projects, board)


def test_board_is_parsed(dataset):
    rs = dataset.resourcing
    assert rs.title == "Foresight Board — Saffron"
    assert len(rs.workstreams) == 14
    ws = rs.workstreams[0]
    assert (ws.name, ws.group) == ("Stock Sync", "Project Saffron")
    assert ws.note.startswith("Two stories at risk")
    assert [d.label for d in ws.delivery_points][-4:] == ["Nov '26", "Dec '26", "Jan '27", "Unscheduled"]
    assert ws.delivery_points[-1].month is None
    assert {a.employment for w in rs.workstreams for a in w.allocations} == {"permanent", "contract", "unknown"}
    weeks = {a.week for w in rs.workstreams for a in w.allocations}
    assert min(weeks) == date(2026, 11, 23) and all(w.weekday() == 0 for w in weeks)
    assert rs.workstreams[-1].group == "Other workstreams"


def test_tool_flag_matches_computed_over_allocation(dataset):
    """The generator marks chips "over" when a person's weekly total > 100%; our computation must agree."""
    from app.analytics.resourcing import over_allocations
    rows = over_allocations(dataset.resourcing)["rows"]
    assert rows and all(r["total_percent"] > 100 and r["flagged_by_tool"] for r in rows)


def test_issue_pages_are_mapped(dataset):
    keys = {p.project.key for p in dataset.projects}
    assert keys == {"K41", "K42", "M07", "T19"}
    issues = [i for p in dataset.projects for i in p.issues]
    assert sum(i.kind.value == "epic" for i in issues) == 9
    stories = [i for i in issues if i.kind.value == "story"]
    assert len(stories) == 30 and all(i.epic_key for i in stories)  # parent key resolves to an epic
    assert sum(bool(i.links) for i in stories) == 6


@pytest.mark.parametrize("question,tool", [
    ("Give me the current project status and identify delayed epics", "project_status"),
    ("Who is over-allocated next week?", "over_allocated_people"),
    ("what is priya working on", "person_schedule"),
    ("Tell me about Stock Sync", "workstream_details"),
    ("What is outstanding for December 2026?", "outstanding_work"),
    ("Which milestones are coming up?", "upcoming_milestones"),
    ("What are the major blockers?", "blockers"),
    ("Which tasks are overdue?", "overdue_issues"),
    ("Which epics are delayed?", "delayed_epics"),
    ("What is K41-3157 about?", "issue_details"),
    ("Which tasks are assigned to Lucia Doe?", "assigned_issues"),
    ("How many stories are in progress?", "project_status"),
    ("What milestones are next week?", "upcoming_milestones"),
    ("tell me a joke", "help"),
])
def test_demo_routing(dataset, question, tool):
    assert demo.route(Toolset(dataset), question)[0] == tool


def test_demo_answers_are_grounded(dataset):
    ts = Toolset(dataset)
    for q in ["Give me the current project status and identify delayed epics", "Who is over-allocated next week?",
              "What is Priya working on?", "Tell me about Stock Sync", "What is outstanding for Dec?",
              "Which milestones are coming up?", "What are the blockers?", "Which tasks are overdue?"]:
        a = demo.answer(ts, q)
        assert a.mode == "demo" and a.text
        assert llm.ungrounded_keys(a.text, [], a.evidence) == [], q


def test_unknown_person_is_reported_not_guessed(dataset):
    a = demo.answer(Toolset(dataset), "show me the schedule for Nobody Doe")
    assert "help" not in a.tools_used


def test_parse_month():
    assert parse_month("Dec", date(2026, 11, 23)) == date(2026, 12, 1)
    assert parse_month("Jan", date(2026, 11, 23)) == date(2027, 1, 1)
    assert parse_month("Nov '26", date(2026, 11, 23)) == date(2026, 11, 1)
    assert board_month("Jan '27") == date(2027, 1, 1)
    assert board_month("Unscheduled") is None


class FakeToolModel(GenericFakeChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


def test_llm_mode_uses_tools_and_rejects_invented_keys(dataset):
    ts = Toolset(dataset)
    call = AIMessage("", tool_calls=[{"name": "overdue_issues", "args": {}, "id": "1"}])
    overdue = ts.overdue_issues()
    real_key = overdue["evidence"][0]["label"]

    good = FakeToolModel(messages=iter([call, AIMessage(f"{real_key} is overdue.")]))
    a = llm.answer(ts, "what is overdue?", [], model=good)
    assert (a.mode, a.tools_used) == ("llm", ["overdue_issues"])
    claim, *rows = a.text.split("\n")
    assert claim == f"{real_key} is overdue."  # the model writes only the claim...
    assert rows and all(r.startswith("- ") for r in rows)  # ...the proof rows come from code, one per overdue issue
    assert len(rows) == len(overdue["issues"])
    assert real_key in {e["label"] for e in a.evidence}

    invented = FakeToolModel(messages=iter([call, AIMessage("ZZZ-999 is overdue."), AIMessage("ZZZ-998 too.")]))
    a = llm.answer(ts, "what is overdue?", [], model=invented)
    assert "couldn't verify" in a.text


def test_ingest_then_chat_api():
    client = TestClient(app)
    res = client.post("/api/v1/sources/utility/ingest", json=SCAN)
    assert res.status_code == 200
    body = res.json()
    assert body["board"]["workstreams"] == 14 and len(body["projects"]) == 4
    ds = body["dataset_id"]

    status = client.get("/api/v1/chat/status", params={"dataset_id": ds}).json()
    assert status["mode"] == "demo" and len(status["suggestions"]) == 5

    reply = client.post("/api/v1/chat", json={"dataset_id": ds, "message": "Who is over-allocated next week?"})
    assert reply.status_code == 200 and reply.json()["evidence"]

    assert client.post("/api/v1/chat", json={"dataset_id": "missing-dataset", "message": "hi"}).status_code == 404
    assert client.post("/api/v1/chat", json={"dataset_id": ds, "message": ""}).status_code == 422
