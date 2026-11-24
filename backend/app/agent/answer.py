from dataclasses import dataclass, field
from typing import Literal


@dataclass
class ChatAnswer:
    text: str
    mode: Literal["demo", "llm"]
    evidence: list[dict[str, str]] = field(default_factory=list)
    tools_used: list[str] = field(default_factory=list)
