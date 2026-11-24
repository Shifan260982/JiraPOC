"""Text mode: model fallback on failures, and code-chosen data with model-written summary."""

import io
import json
import urllib.error
from pathlib import Path

import pytest

from app import store
from app.agent import text_llm
from app.agent.tools import Toolset
from app.connectors.utility_app.foresight import map_foresight
from app.connectors.utility_app.mapper import UtilityScan, map_scan
from app.main import load_dotenv

SCAN = json.loads((Path(__file__).parent / "fixtures" / "sample_scan.json").read_text(encoding="utf-8"))


@pytest.fixture
def ts():
    scan = UtilityScan.model_validate(SCAN)
    return Toolset(store.put(map_scan(scan)[0], map_foresight(scan)[0]))


class FakeHTTP:
    """Stands in for urlopen: replies per model from a script, records the order models were tried."""

    def __init__(self, replies):
        self.replies, self.tried, self.prompts = replies, [], []

    def __call__(self, req, timeout):
        body = json.loads(req.data)
        self.tried.append(body["model"])
        self.prompts.append(body["messages"][-1]["content"])
        reply = self.replies[body["model"]]
        if isinstance(reply, int):
            raise urllib.error.HTTPError(req.full_url, reply, "error", {}, io.BytesIO(b"{}"))
        return io.BytesIO(json.dumps({"choices": [{"message": {"content": reply}, "finish_reason": "stop"}]}).encode())


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setenv("NVIDIA_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MODELS", "a/first,b/second")

    def install(replies):
        fake = FakeHTTP(replies)
        monkeypatch.setattr(text_llm.urllib.request, "urlopen", fake)
        return fake
    return install


def test_falls_back_to_next_model_on_rate_limit(api):
    fake = api({"a/first": 429, "b/second": "Fine."})
    assert text_llm.complete([{"role": "user", "content": "hi"}]) == ("Fine.", "b/second")
    assert fake.tried == ["a/first", "b/second"]


def test_all_models_failing_raises(api):
    api({"a/first": 410, "b/second": 500})
    with pytest.raises(text_llm.LLMUnavailable, match="HTTP 410.*HTTP 500"):
        text_llm.complete([{"role": "user", "content": "hi"}])


def test_reasoning_tags_are_stripped(api):
    api({"a/first": "<think>let me see</think> Yes."})
    assert text_llm.complete([{"role": "user", "content": "hi"}])[0] == "Yes."


def test_code_picks_the_data_and_rows_come_from_code(api, ts):
    fake = api({"a/first": "Felix and Mei are over-allocated next week."})
    a = text_llm.answer(ts, "Who is over-allocated next week?", [])
    claim, *rows = a.text.split("\n")
    assert claim == "Felix and Mei are over-allocated next week."
    assert a.tools_used == ["over_allocated_people"] and rows and all(r.startswith("- ") for r in rows)
    assert "Felix D." in fake.prompts[0]  # the model was given the computed data


def test_invented_issue_key_is_replaced_by_computed_claim(api, ts):
    api({"a/first": "ZZZ-999 is the delayed epic."})
    a = text_llm.answer(ts, "Which epics are delayed?", [])
    assert "ZZZ-999" not in a.text and a.text.startswith("3 delayed epics")


def test_unmatched_question_answers_from_overview(api, ts):
    api({"a/first": "NOT IN DATA"})
    a = text_llm.answer(ts, "What is the meaning of life?", [])
    assert a.tools_used == ["project_status"] and a.text == text_llm.NOT_ANSWERED


class ScriptedHTTP(FakeHTTP):
    """Replies from a list in call order, regardless of model."""

    def __init__(self, replies):
        super().__init__({})
        self.queue = list(replies)

    def __call__(self, req, timeout):
        self.replies = {json.loads(req.data)["model"]: self.queue.pop(0)}
        return super().__call__(req, timeout)


def test_routed_tool_that_cannot_answer_retries_with_retrieval(api, ts, monkeypatch):
    api({})
    fake = ScriptedHTTP(["The data does not answer the question.", "Stock Sync has a bug open on staging."])
    monkeypatch.setattr(text_llm.urllib.request, "urlopen", fake)
    a = text_llm.answer(ts, "Which workstreams have bugs on staging?", [])
    assert a.text == "Stock Sync has a bug open on staging."
    assert "workstream_details" in a.tools_used and "on staging" in fake.prompts[1]


def test_unmatched_question_retrieves_relevant_chunks(api, ts):
    fake = api({"a/first": "Stock Sync is waiting on a supplier data refresh."})
    a = text_llm.answer(ts, "Is anything waiting on supplier data?", [])
    assert a.text == "Stock Sync is waiting on a supplier data refresh."  # the model's text is the whole answer
    assert a.tools_used[0] == "project_status" and "workstream_details" in a.tools_used
    assert "awaiting supplier data refresh" in fake.prompts[0]  # the matching workstream note was retrieved
    assert len(fake.prompts[0]) < text_llm.MAX_CONTEXT_CHARS + 200


def test_context_answer_with_invented_key_falls_back_to_overview(api, ts):
    api({"a/first": "ZZZ-999 is waiting on supplier data."})
    a = text_llm.answer(ts, "Is anything waiting on supplier data?", [])
    assert "ZZZ-999" not in a.text and a.text.startswith("Status of")


def test_load_dotenv_keeps_real_env(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text('# comment\nNEW_VAR="from-file"\nKEEP_VAR=from-file\n', encoding="utf-8")
    monkeypatch.delenv("NEW_VAR", raising=False)
    monkeypatch.setenv("KEEP_VAR", "from-env")
    load_dotenv(env)
    import os
    assert (os.environ["NEW_VAR"], os.environ["KEEP_VAR"]) == ("from-file", "from-env")
    monkeypatch.delenv("NEW_VAR")
