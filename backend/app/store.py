"""In-memory store of ingested datasets, so the chat can answer from the latest scan.

shortcut: single process, lost on restart, no per-user separation; move to PostgreSQL with per-user keys (ARCHITECTURE §7)
before anyone but the developer uses the backend.
"""

import secrets
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from threading import Lock

from app.domain.schema import ProjectSnapshot, ResourcingSnapshot

MAX_DATASETS = 20


@dataclass(frozen=True)
class Dataset:
    id: str
    created: datetime
    projects: list[ProjectSnapshot] = field(default_factory=list)
    resourcing: ResourcingSnapshot | None = None


_datasets: OrderedDict[str, Dataset] = OrderedDict()
_lock = Lock()


def put(projects: list[ProjectSnapshot], resourcing: ResourcingSnapshot | None) -> Dataset:
    ds = Dataset(id=secrets.token_urlsafe(16), created=datetime.now(UTC), projects=projects, resourcing=resourcing)
    with _lock:
        _datasets[ds.id] = ds
        while len(_datasets) > MAX_DATASETS:
            _datasets.popitem(last=False)
    return ds


def get(dataset_id: str) -> Dataset | None:
    with _lock:
        return _datasets.get(dataset_id)
