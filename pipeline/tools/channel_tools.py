"""Channel-aware tools — self-awareness across past episodes."""

from __future__ import annotations

from .. import db


def list_recent_videos(profile_name: str, limit: int = 10) -> dict:
    """List the channel's recent successful videos. Use to (a) avoid
    repeating angles already covered, (b) make callbacks to past
    episodes for series continuity, (c) understand the channel's recent
    voice/cadence by sampling existing thesis/title patterns.

    Args:
        profile_name: Channel profile slug, e.g. "shanyang-cn" or
                      "world-watching-cn".
        limit: How many recent videos to list (default 10, max 30).

    Returns:
        dict with `profile_name`, `count`, and `videos` (list of {title,
        thesis, description, url_slug, ready_at, output_count}). Empty
        list if the channel is brand new.
    """
    limit = max(1, min(int(limit), 30))
    try:
        with db.cursor() as cur:
            cur.execute(
                """
                SELECT
                    o.title                         AS title,
                    o.description                   AS description,
                    j.edl_jsonb ->> 'thesis_zh'     AS thesis,
                    j.edl_jsonb ->> 'url_slug'      AS url_slug,
                    s.external_id                   AS external_id,
                    o.ready_at                      AS ready_at,
                    o.id                            AS output_id
                  FROM outputs o
                  JOIN jobs j   ON j.id = o.job_id
                  JOIN profiles p ON p.id = j.profile_id
                  LEFT JOIN sources s
                       ON s.id = NULLIF(j.edl_jsonb ->> 'source_id', '')::bigint
                  WHERE p.name = %s
                    AND o.status = 'ready'
                  ORDER BY o.ready_at DESC NULLS LAST, o.id DESC
                  LIMIT %s
                """,
                (profile_name, limit),
            )
            rows = cur.fetchall()
    except Exception as e:
        return {"profile_name": profile_name, "error": f"query failed: {e}",
                "videos": []}

    videos = []
    for r in rows:
        slug = r.get("url_slug") or r.get("external_id") or f"output-{r.get('output_id')}"
        videos.append({
            "title": r.get("title") or "(untitled)",
            "thesis": r.get("thesis"),
            "description": r.get("description"),
            "url_slug": slug,
            "ready_at": r.get("ready_at").isoformat() if r.get("ready_at") else None,
        })
    return {
        "profile_name": profile_name,
        "count": len(videos),
        "videos": videos,
    }
