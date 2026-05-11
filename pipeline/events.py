"""Run lifecycle + per-stage event emitter.

A `run` is one operator-initiated produce attempt — created at the very
top of produce.py / produce-original.py and carried via `--run-id` into
the subprocess chain (discovery, edl-prototype, edl-render). Every
meaningful stage transition emits a row into `run_events` so the web
layer can render a live timeline.

All functions are best-effort: if the DB is unreachable we swallow the
error and log to stderr. The pipeline must never crash because event
logging failed.
"""

from __future__ import annotations

import json
import sys
import traceback
from typing import Any

from . import db


def _safe(fn, *args, **kwargs):
    """Run a DB call, swallow errors. Returns None on failure."""
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        print(f"[events] {fn.__name__} failed: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)
        return None


def start_run(
    *,
    profile_id: int,
    kind: str,
    topic_title: str,
    url_slug: str | None = None,
) -> int | None:
    """Create a new run row. Returns run_id, or None if the insert failed."""
    def _do():
        with db.cursor() as cur:
            cur.execute(
                """
                INSERT INTO runs (profile_id, kind, topic_title, url_slug, status, current_stage)
                VALUES (%s, %s, %s, %s, 'running', 'starting')
                RETURNING id
                """,
                (profile_id, kind, topic_title, url_slug),
            )
            return cur.fetchone()["id"]
    return _safe(_do)


def emit(
    run_id: int | None,
    stage: str,
    status: str = "info",
    message: str | None = None,
    **metadata: Any,
) -> None:
    """Append a run event. `status` is one of start|done|fail|skip|info.

    metadata is any JSON-serializable kwargs (e.g. shot_idx=3, duration_sec=7.2).
    """
    if run_id is None:
        return
    def _do():
        with db.cursor() as cur:
            cur.execute(
                """
                INSERT INTO run_events (run_id, stage, status, message, metadata)
                VALUES (%s, %s, %s, %s, %s::jsonb)
                """,
                (
                    run_id,
                    stage,
                    status,
                    message,
                    json.dumps(metadata, ensure_ascii=False, default=str) if metadata else None,
                ),
            )
            cur.execute(
                "UPDATE runs SET current_stage = %s WHERE id = %s",
                (f"{stage}:{status}", run_id),
            )
    _safe(_do)


def attach_topic(run_id: int | None, topic_id: int) -> None:
    if run_id is None:
        return
    def _do():
        with db.cursor() as cur:
            cur.execute(
                "UPDATE runs SET topic_id = %s WHERE id = %s",
                (topic_id, run_id),
            )
    _safe(_do)


def attach_job(run_id: int | None, job_id: int) -> None:
    if run_id is None:
        return
    def _do():
        with db.cursor() as cur:
            cur.execute(
                "UPDATE runs SET job_id = %s WHERE id = %s",
                (job_id, run_id),
            )
    _safe(_do)


def attach_slug(run_id: int | None, url_slug: str) -> None:
    if run_id is None:
        return
    def _do():
        with db.cursor() as cur:
            cur.execute(
                "UPDATE runs SET url_slug = %s WHERE id = %s",
                (url_slug, run_id),
            )
    _safe(_do)


def finish_run(
    run_id: int | None,
    status: str,
    error_message: str | None = None,
) -> None:
    """Mark the run terminal. status: completed|failed|skipped.

    Only writes if the run is still in 'running' state — so an atexit hook
    fired after an explicit finish_run won't overwrite the terminal state.
    """
    if run_id is None:
        return
    def _do():
        with db.cursor() as cur:
            cur.execute(
                """
                UPDATE runs
                SET status = %s,
                    error_message = %s,
                    finished_at = NOW(),
                    current_stage = %s
                WHERE id = %s AND status = 'running'
                """,
                (status, error_message, status, run_id),
            )
    _safe(_do)


def register_atexit(run_id: int | None) -> None:
    """Register an atexit hook that marks the run failed if it never
    reached a terminal state (e.g. the script crashed without calling
    finish_run, or was Ctrl-C'd mid-pipeline). No-op if run already
    finished — finish_run's WHERE clause guards against double-writes."""
    if run_id is None:
        return
    import atexit
    atexit.register(
        finish_run, run_id, "failed", "process exited without finishing run"
    )
