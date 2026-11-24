import logging
import os
from dataclasses import asdict
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app import store
from app.agent import demo, llm, text_llm
from app.agent.tools import Toolset
from app.analytics import resourcing

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/chat", tags=["chat"])


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    content: Annotated[str, Field(max_length=8_000)]


class ChatRequest(BaseModel):
    dataset_id: Annotated[str, Field(min_length=8, max_length=64)]
    message: Annotated[str, Field(min_length=1, max_length=2_000)]
    history: list[Turn] = Field(default=[], max_length=20)


def _engine() -> Literal["text", "agent", "demo"]:
    """text: hosted text model writes the summary (NVIDIA by default); agent: tool-calling model (e.g. Ollama)."""
    provider = os.getenv("LLM_PROVIDER", "").lower()
    if provider in ("nvidia", "openai_compatible") or (not provider and text_llm.api_key()):
        return "text"
    return "agent" if llm.configured() else "demo"


def _model_label(engine: str) -> str | None:
    return {"text": (text_llm.models() or [None])[0], "agent": os.getenv("LLM_MODEL")}.get(engine)


def _dataset(dataset_id: str) -> store.Dataset:
    ds = store.get(dataset_id)
    if ds is None:
        raise HTTPException(404, "This data is no longer on the server. Read the tool again from the side panel.")
    return ds


@router.get("/status")
def chat_status(dataset_id: str) -> dict[str, Any]:
    """What the chat can answer from, and data-specific example questions."""
    ds = _dataset(dataset_id)
    suggestions = ["Give me the current project status and identify delayed epics"] if ds.projects else []
    if rs := ds.resourcing:
        everyone = resourcing.people(rs)
        suggestions += ["Who is over-allocated next week?"]
        if everyone:
            suggestions.append(f"What is {everyone[0].split()[0]} working on?")
        if rs.workstreams:
            suggestions.append(f"Tell me about {rs.workstreams[0].name}")
        suggestions += ["Which milestones are coming up?"]
    if ds.projects:
        suggestions += ["What are the blockers?"]
    return {
        "mode": "demo" if (engine := _engine()) == "demo" else "llm",
        "model": _model_label(engine),
        "as_of": (ds.resourcing.as_of if ds.resourcing else ds.projects[0].as_of if ds.projects else None),
        "projects": [p.project.key for p in ds.projects],
        "workstreams": len(ds.resourcing.workstreams) if ds.resourcing else 0,
        "suggestions": suggestions[:5],
    }


@router.post("")
def chat(req: ChatRequest) -> dict[str, Any]:
    ts = Toolset(_dataset(req.dataset_id))
    engine = _engine()
    if engine != "demo":
        answer = text_llm.answer if engine == "text" else llm.answer
        try:
            result = answer(ts, req.message, [t.model_dump() for t in req.history])
        except Exception:  # provider outage or misconfiguration: fall back rather than fail the user
            log.exception("LLM call failed; answering in demo mode")
            result = demo.answer(ts, req.message)
            result.text = "The language model is unavailable, so this is a basic answer.\n\n" + result.text
    else:
        result = demo.answer(ts, req.message)
    log.info("chat mode=%s tools=%s evidence=%d", result.mode, result.tools_used, len(result.evidence))
    return asdict(result)
