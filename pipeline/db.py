"""Postgres write path for the pipeline.

The schema lives in db/schema.sql. This module wraps the inserts the
scripts need so they don't all hand-roll SQL. Reads are kept on
`pipeline.profiles` (Profile fetch) and the web app (`lib/jobs.ts`).

Connection params come from the same env vars `pipeline.profiles` uses,
so a single `source ~/.config/youtube-clips.env` covers both modules.
"""

from __future__ import annotations

import json
import os
from contextlib import contextmanager
from typing import Any, Iterator

import psycopg2
import psycopg2.extras


def _connect():
    return psycopg2.connect(
        host=os.environ.get("PG_HOST", "127.0.0.1"),
        port=int(os.environ.get("PG_PORT", "5432")),
        user=os.environ.get("YOUTUBE_CLIPS_PG_USER", "youtube_clips"),
        password=os.environ["YOUTUBE_CLIPS_PG_PASSWORD"],
        dbname=os.environ.get("YOUTUBE_CLIPS_PG_DB", "youtube_clips"),
    )


@contextmanager
def cursor() -> Iterator[psycopg2.extras.RealDictCursor]:
    conn = _connect()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            yield cur
        conn.commit()
    finally:
        conn.close()


# ---- topics --------------------------------------------------------------

def upsert_topic(
    *,
    profile_id: int,
    title: str,
    description: str | None = None,
    keywords: list[str] | None = None,
    status: str = "approved",
    source: str = "agent",
) -> int:
    """Look up a Topic by (profile_id, title); insert if missing.

    The schema lacks a UNIQUE constraint here on purpose — Phase 2 wants
    the freedom to re-discover the same topic later under a different
    framing — so we do a SELECT-then-INSERT rather than ON CONFLICT.
    """
    with cursor() as cur:
        cur.execute(
            "SELECT id FROM topics WHERE profile_id = %s AND title = %s "
            "ORDER BY id DESC LIMIT 1",
            (profile_id, title),
        )
        row = cur.fetchone()
        if row:
            return row["id"]
        cur.execute(
            """
            INSERT INTO topics (profile_id, title, description, keywords, status, source, approved_at)
            VALUES (%s, %s, %s, %s, %s, %s, NOW())
            RETURNING id
            """,
            (
                profile_id,
                title,
                description,
                keywords or [],
                status,
                source,
            ),
        )
        return cur.fetchone()["id"]


# ---- sources -------------------------------------------------------------

def upsert_source(
    *,
    profile_id: int,
    source_platform: str,
    external_id: str,
    url: str,
    title: str | None = None,
    channel: str | None = None,
    duration_sec: int | None = None,
    source_language: str | None = None,
    metadata: dict | None = None,
    download_path: str | None = None,
    downloaded: bool = False,
) -> int:
    """The (source_platform, external_id) pair has a UNIQUE constraint;
    we ON CONFLICT DO UPDATE on it so a second discover for the same
    YouTube id refreshes the metadata.
    """
    with cursor() as cur:
        cur.execute(
            """
            INSERT INTO sources (
                profile_id, source_platform, external_id, url,
                title, channel, duration_sec, source_language,
                metadata_jsonb, download_path, downloaded_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s,
                %s::jsonb, %s,
                CASE WHEN %s THEN NOW() ELSE NULL END
            )
            ON CONFLICT (source_platform, external_id) DO UPDATE SET
                title         = COALESCE(EXCLUDED.title, sources.title),
                channel       = COALESCE(EXCLUDED.channel, sources.channel),
                duration_sec  = COALESCE(EXCLUDED.duration_sec, sources.duration_sec),
                metadata_jsonb = COALESCE(EXCLUDED.metadata_jsonb, sources.metadata_jsonb),
                download_path = COALESCE(EXCLUDED.download_path, sources.download_path),
                downloaded_at = COALESCE(EXCLUDED.downloaded_at, sources.downloaded_at)
            RETURNING id
            """,
            (
                profile_id, source_platform, external_id, url,
                title, channel, duration_sec, source_language,
                json.dumps(metadata) if metadata else None,
                download_path,
                downloaded,
            ),
        )
        return cur.fetchone()["id"]


def mark_source_downloaded(*, source_platform: str, external_id: str, path: str) -> None:
    with cursor() as cur:
        cur.execute(
            """
            UPDATE sources
            SET download_path = %s, downloaded_at = NOW()
            WHERE source_platform = %s AND external_id = %s
            """,
            (path, source_platform, external_id),
        )


# ---- jobs ----------------------------------------------------------------

def insert_job(
    *,
    topic_id: int,
    profile_id: int,
    edl_jsonb: dict,
    status: str = "completed",
    parent_job_id: int | None = None,
) -> int:
    with cursor() as cur:
        cur.execute(
            """
            INSERT INTO jobs (
                topic_id, profile_id, edl_jsonb, parent_job_id,
                status, started_at, completed_at
            ) VALUES (
                %s, %s, %s::jsonb, %s,
                %s, NOW(), CASE WHEN %s = 'completed' THEN NOW() ELSE NULL END
            )
            RETURNING id
            """,
            (
                topic_id, profile_id,
                json.dumps(edl_jsonb, ensure_ascii=False),
                parent_job_id,
                status, status,
            ),
        )
        return cur.fetchone()["id"]


# ---- outputs -------------------------------------------------------------

def insert_output(
    *,
    job_id: int,
    platform: str,
    aspect_ratio: str,
    language: str,
    path: str,
    duration_sec: float | None = None,
    file_size_bytes: int | None = None,
    title: str | None = None,
    description: str | None = None,
    tags: list[str] | None = None,
    status: str = "ready",
) -> int:
    with cursor() as cur:
        cur.execute(
            """
            INSERT INTO outputs (
                job_id, platform, aspect_ratio, language,
                path, duration_sec, file_size_bytes,
                title, description, tags, status, ready_at
            ) VALUES (
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s, %s,
                CASE WHEN %s = 'ready' THEN NOW() ELSE NULL END
            )
            ON CONFLICT (job_id, platform) DO UPDATE SET
                path            = EXCLUDED.path,
                duration_sec    = EXCLUDED.duration_sec,
                file_size_bytes = EXCLUDED.file_size_bytes,
                title           = EXCLUDED.title,
                description     = EXCLUDED.description,
                tags            = EXCLUDED.tags,
                status          = EXCLUDED.status,
                ready_at        = CASE WHEN EXCLUDED.status = 'ready' THEN NOW() ELSE outputs.ready_at END
            RETURNING id
            """,
            (
                job_id, platform, aspect_ratio, language,
                path, duration_sec, file_size_bytes,
                title, description, tags or [], status, status,
            ),
        )
        return cur.fetchone()["id"]
