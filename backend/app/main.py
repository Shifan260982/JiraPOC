"""FastAPI entry point.

shortcut: no user authentication yet (D5, Entra ID) and no CORS. Run bound to 127.0.0.1 only; add auth before
deploying anywhere shared. The extension needs no CORS because it holds host permission for the backend origin.
"""

import logging
import os
from pathlib import Path

from fastapi import FastAPI

from app.api import chat, sources

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


def load_dotenv(path: Path = Path(__file__).resolve().parents[2] / ".env") -> None:
    """Read KEY=value lines from the project-root .env; real environment variables win. Values are never logged."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        if sep and key.strip() and not key.lstrip().startswith("#"):
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_dotenv()

app = FastAPI(title="Jira Reporting Assistant", version="0.1.0")
app.include_router(sources.router)
app.include_router(chat.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
