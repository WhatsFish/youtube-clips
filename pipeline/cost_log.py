"""Best-effort cost-event logger.

Mirrors the fleet convention from ai-feed / stock-analyst: one row per
billable AI call lands in the shared `cost_tracker.cost_event` table.

Env vars (typically sourced via `~/.config/cost-tracker.env`, or
re-exported in `~/.config/youtube-clips.env`):
  COST_PG_HOST / COST_PG_PORT / COST_PG_USER / COST_PG_PASSWORD / COST_PG_DB

If the env vars aren't set, all log calls become no-ops. We never throw
out of this module — a cost-log failure must not break the pipeline.

Pricing constants are deliberately conservative estimates; revisit when
Volcengine publishes finalized 2026 rates. The dashboard is directionally
correct; if you need precise billing, the Volcengine console is canonical.
"""

from __future__ import annotations

import os
import sys
import time
import traceback
from contextlib import contextmanager
from typing import Any

try:
    import psycopg2
    import psycopg2.extras
except ImportError:
    psycopg2 = None  # type: ignore


# Volcengine Doubao Seedance 1.5 Pro estimated rates.
# Source: Volcengine official pricing page as of late 2025, pay-as-you-go.
# 720p: ¥0.10/sec ≈ $0.014/sec  (1 USD ≈ 7.2 CNY)
# 1080p: ¥0.17/sec ≈ $0.024/sec
# 480p: estimated ¥0.05/sec ≈ $0.007/sec
DOUBAO_RATES_USD_PER_SEC: dict[str, float] = {
    "480p": 0.007,
    "720p": 0.014,
    "1080p": 0.024,
}


def estimate_doubao_cost_usd(
    duration_sec: float,
    resolution: str = "720p",
) -> float | None:
    rate = DOUBAO_RATES_USD_PER_SEC.get(resolution.lower())
    if rate is None:
        return None
    return round(rate * duration_sec, 6)


def _enabled() -> bool:
    return bool(os.environ.get("COST_PG_PASSWORD")) and psycopg2 is not None


@contextmanager
def _connect():
    conn = psycopg2.connect(
        host=os.environ.get("COST_PG_HOST", "127.0.0.1"),
        port=int(os.environ.get("COST_PG_PORT", "5432")),
        user=os.environ.get("COST_PG_USER", "cost_tracker"),
        password=os.environ["COST_PG_PASSWORD"],
        dbname=os.environ.get("COST_PG_DB", "cost_tracker"),
    )
    try:
        with conn.cursor() as cur:
            yield cur
        conn.commit()
    finally:
        conn.close()


def log_event(
    *,
    service: str,
    provider: str,
    model: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    cost_usd: float | None = None,
    duration_ms: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Best-effort INSERT into cost_event. Never throws; logs to stderr on failure."""
    if not _enabled():
        return
    import json
    try:
        with _connect() as cur:
            cur.execute(
                """
                INSERT INTO cost_event
                  (service, provider, model, input_tokens, output_tokens,
                   cost_usd, duration_ms, metadata)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                """,
                (
                    service, provider, model,
                    input_tokens, output_tokens,
                    cost_usd, duration_ms,
                    json.dumps(metadata or {}, ensure_ascii=False, default=str),
                ),
            )
    except Exception as e:
        print(f"[cost-log] insert failed: {e}", file=sys.stderr)
        traceback.print_exc(file=sys.stderr)


# Doubao 1.0-pro-fast bills by output tokens, not seconds. As of 2026-05:
# 0.0042 元 / 1000 tokens, ~7.2 RMB/USD → ~5.83e-7 USD/token
DOUBAO_RMB_PER_K_TOKENS = 0.0042
RMB_PER_USD = 7.2


def log_doubao_video(
    *,
    duration_sec: float,
    resolution: str,
    wall_clock_sec: float,
    model: str,
    run_id: int | None = None,
    shot_idx: int | None = None,
    task_id: str | None = None,
    prompt: str | None = None,
    total_tokens: int | None = None,
) -> None:
    """Convenience wrapper for Doubao Seedance video generation calls.

    Pricing model depends on the Doubao tier:
    - 1.5-pro / 1.0-pro: per-sec by resolution (DOUBAO_RATES_USD_PER_SEC)
    - 1.0-pro-fast: per-token (DOUBAO_RMB_PER_K_TOKENS, requires
      `total_tokens` from response.usage).
    """
    if total_tokens and "pro-fast" in (model or ""):
        cost = round(total_tokens * DOUBAO_RMB_PER_K_TOKENS / 1000 / RMB_PER_USD, 6)
    else:
        cost = estimate_doubao_cost_usd(duration_sec, resolution)
    md: dict[str, Any] = {
        "duration_sec": duration_sec,
        "resolution": resolution,
        "task_id": task_id,
    }
    if total_tokens:
        md["total_tokens"] = total_tokens
    if run_id is not None:
        md["run_id"] = run_id
    if shot_idx is not None:
        md["shot_idx"] = shot_idx
    if prompt:
        md["prompt"] = prompt[:500]
    log_event(
        service="youtube-clips-doubao",
        provider="volcengine",
        model=model,
        cost_usd=cost,
        duration_ms=int(wall_clock_sec * 1000),
        metadata=md,
    )
