"""Profile fetcher.

Profiles live in the `profiles` table of the youtube_clips Postgres DB.
This module wraps the read path so scripts don't need to know about
SQL or psycopg2 directly.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

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


@dataclass(frozen=True)
class Profile:
    id: int
    name: str
    description: str | None
    config: dict[str, Any]
    active: bool

    def render_block(self) -> str:
        """Render the Profile config as a JSON block for inclusion in a
        prompt. We omit transient/operational fields if any get added
        later that shouldn't bleed into the LLM context.
        """
        return json.dumps(self.config, ensure_ascii=False, indent=2)

    def get(self, *path: str, default: Any = None) -> Any:
        """Walk a dotted path into config, returning `default` on miss."""
        cur: Any = self.config
        for key in path:
            if not isinstance(cur, dict) or key not in cur:
                return default
            cur = cur[key]
        return cur


def fetch_profile(name: str) -> Profile:
    """Read one Profile by name. Raises ValueError if not found."""
    with _connect() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, name, description, config_jsonb, active
                FROM profiles
                WHERE name = %s
                """,
                (name,),
            )
            row = cur.fetchone()
    if not row:
        raise ValueError(f"profile {name!r} not found")
    return Profile(
        id=row["id"],
        name=row["name"],
        description=row["description"],
        config=row["config_jsonb"],
        active=row["active"],
    )
