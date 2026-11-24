import logging
from typing import Any

from fastapi import APIRouter

from app import store
from app.analytics import resourcing
from app.analytics.metrics import project_overview
from app.connectors.utility_app.foresight import map_foresight
from app.connectors.utility_app.mapper import UtilityScan, map_scan

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/sources", tags=["sources"])


@router.post("/utility/ingest")
def ingest_utility_scan(scan: UtilityScan) -> dict[str, Any]:
    """Normalise tables scanned by the extension from the utility tool, store them for the chat, and summarise."""
    snapshots, warnings, stats = map_scan(scan)
    board, board_warnings = map_foresight(scan)
    warnings += board_warnings
    if not snapshots and board is None:
        warnings.append("No Jira issue tables or resourcing board were found on the scanned pages.")
    dataset = store.put(snapshots, board)
    stats["workstreams"] = len(board.workstreams) if board else 0
    log.info("Utility scan ingested: dataset=%s %s, %d warning type(s)", dataset.id, stats, len(warnings))
    return {
        "dataset_id": dataset.id,
        "projects": [
            {
                "key": s.project.key,
                "name": s.project.name,
                "overview": project_overview(s),
                "snapshot": s.model_dump(mode="json"),
            }
            for s in snapshots
        ],
        "board": (
            {**{k: v for k, v in resourcing.board_overview(board).items() if k != "evidence"},
             "snapshot": board.model_dump(mode="json")}
            if board else None
        ),
        "warnings": warnings,
        "stats": stats,
    }
