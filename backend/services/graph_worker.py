"""지식 그래프 백그라운드 작업자 — pending 노트를 하나씩 추출한다.

- 마지막 수정 후 QUIET_SECONDS가 지난 노트만 처리 (편집 중에는 호출하지 않음)
- 모델 호출은 분당 RATE_PER_MINUTE개 이하
"""
import logging
import os
import threading
import time
from datetime import datetime, timedelta, timezone

from db import get_conn
from services import graph_extraction

logger = logging.getLogger(__name__)

QUIET_SECONDS = 60
RATE_PER_MINUTE = 10
POLL_SECONDS = 5

_thread: threading.Thread | None = None
_stop = threading.Event()


def next_ready_note(now: datetime | None = None) -> str | None:
    """처리할 차례인 pending 노트 id (가장 오래 기다린 것부터)."""
    now = now or datetime.now(timezone.utc)
    cutoff = (now - timedelta(seconds=QUIET_SECONDS)).isoformat()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id FROM notes WHERE graph_status = 'pending' AND is_archived = 0 "
            "AND modified_at <= ? ORDER BY modified_at LIMIT 1",
            (cutoff,),
        ).fetchone()
    return row["id"] if row else None


def _run() -> None:
    min_interval = 60.0 / RATE_PER_MINUTE
    last_call = 0.0
    while not _stop.is_set():
        try:
            note_id = next_ready_note()
            if note_id is None:
                _stop.wait(POLL_SECONDS)
                continue
            wait = last_call + min_interval - time.monotonic()
            if wait > 0:
                _stop.wait(wait)
                if _stop.is_set():
                    break
            last_call = time.monotonic()
            status = graph_extraction.process_note(note_id)
            logger.info("graph extraction %s -> %s", note_id, status)
        except Exception:  # 작업자는 죽지 않고 계속 돈다
            logger.exception("graph worker loop error")
            _stop.wait(POLL_SECONDS)


def start() -> None:
    """작업자 스레드 시작 (중복 시작 무시). SPACENOTE_GRAPH_WORKER=0이면 끈다."""
    global _thread
    if os.getenv("SPACENOTE_GRAPH_WORKER", "1") == "0":
        return
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_run, name="graph-worker", daemon=True)
    _thread.start()


def stop() -> None:
    _stop.set()
