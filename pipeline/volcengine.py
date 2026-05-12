"""Volcengine ARK (Doubao Seedance) text-to-video client.

Used by producer mode as the AI-generation tier above the Pexels stock
library — for shots whose visual_brief calls for culturally-specific
Chinese scenes that Pexels can't supply (县城 / 春运 / 中式厨房 / 街边摊
/ etc.) or for stylistic shots where AI-rendered footage beats stock.

The API is async: POST to create a task, GET to poll status. Typical
generation latency is 30-90 s per 5-10 s clip, so we poll every 8 s.
The completed task response carries a signed video URL valid for 24 h.

Pricing as of 2026-05: doubao-seedance-1-5-pro ≈ ¥1-2 per 5-second 720p
generation (~$0.15-0.30). Cheaper than Sora 2 (~$5/10s); cultural fit
for Chinese-language editorial content is markedly better.

Generated clips include AI-synthesised audio. For our B-roll use case
the renderer overlays narration anyway, so we strip the source audio
during shot rendering (source_has_audio=False), same code path as
Pexels stock.

Required env: VOLC_ARK_API_KEY (Bearer token from ark.volces.com).
"""

from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

ARK_BASE = "https://ark.cn-beijing.volces.com/api/v3"

# Operator switched 2026-05-13 from Seedance-1.5-pro to 1.0-pro-fast
# after 1.5 quota ran out. 1.0-pro-fast is:
#   - Faster: ~24s wall vs 60s for 1.5-pro on 5s 720p
#   - Cheaper: ¥0.0042/1000 tokens (~¥0.44 / 5s 720p clip ≈ $0.06)
#   - User account already has quota
#   - Same async-task API shape
DEFAULT_MODEL = "doubao-seedance-1-0-pro-fast-251015"

# 1.0-pro-fast typically ~20-40s; bump poll a bit for safety.
POLL_INTERVAL_SEC = 8
DEFAULT_TIMEOUT_SEC = 600


@dataclass(frozen=True)
class VideoGenResult:
    task_id: str
    video_url: str
    duration_sec: float
    resolution: str
    seed: int
    has_audio: bool
    total_tokens: int = 0  # 1.0-pro-fast bills by tokens; captured for cost_log


class VolcengineClient:
    def __init__(self, api_key: str | None = None, model: str = DEFAULT_MODEL):
        key = api_key or os.environ.get("VOLC_ARK_API_KEY")
        if not key:
            raise RuntimeError(
                "VOLC_ARK_API_KEY not set. Get a key at https://www.volcengine.com/"
                " (ark console) and add to ~/.config/youtube-clips.env"
            )
        self.api_key = key
        self.model = model

    # ---- HTTP plumbing ----------------------------------------------------

    def _post(self, path: str, body: dict) -> dict:
        req = urllib.request.Request(
            f"{ARK_BASE}{path}",
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())

    def _get(self, path: str) -> dict:
        req = urllib.request.Request(
            f"{ARK_BASE}{path}",
            headers={"Authorization": f"Bearer {self.api_key}"},
        )
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())

    # ---- public API -------------------------------------------------------

    def create_task(
        self,
        prompt: str,
        *,
        duration_sec: int = 10,
        resolution: str = "720p",
        watermark: bool = False,
    ) -> str:
        """Submit a text-to-video task. Inline params (`--duration N`,
        `--resolution`, `--watermark`) are how Doubao's API takes
        generation parameters — they're appended to the prompt text.

        Returns the task id; poll `wait_for_task` for the result.
        """
        full_text = (
            f"{prompt.strip()} "
            f"--duration {duration_sec} "
            f"--resolution {resolution} "
            f"--watermark {'true' if watermark else 'false'}"
        )
        body = {
            "model": self.model,
            "content": [{"type": "text", "text": full_text}],
        }
        r = self._post("/contents/generations/tasks", body)
        task_id = r.get("id")
        if not task_id:
            raise RuntimeError(f"volcengine create_task did not return id: {r}")
        return task_id

    def get_task(self, task_id: str) -> dict:
        return self._get(f"/contents/generations/tasks/{task_id}")

    def wait_for_task(
        self,
        task_id: str,
        *,
        timeout_sec: int = DEFAULT_TIMEOUT_SEC,
        poll_interval_sec: int = POLL_INTERVAL_SEC,
    ) -> VideoGenResult:
        """Block until the task succeeds, fails, or times out.

        Transient network errors during poll (SSL handshake timeout,
        DNS hiccups, transient 5xx) are caught and retried — the task
        is still running on Volcengine's side, we just couldn't read
        its state. Only the overall `timeout_sec` budget kills the poll.
        """
        import urllib.error
        import socket
        deadline = time.monotonic() + timeout_sec
        while time.monotonic() < deadline:
            try:
                r = self.get_task(task_id)
            except (urllib.error.URLError, socket.timeout, ConnectionError) as e:
                print(
                    f"  [doubao poll] transient error: {type(e).__name__}: {e}; "
                    f"retrying in {poll_interval_sec}s",
                    flush=True,
                )
                time.sleep(poll_interval_sec)
                continue
            status = r.get("status")
            if status == "succeeded":
                content = r.get("content") or {}
                video_url = content.get("video_url") or ""
                if not video_url:
                    raise RuntimeError(
                        f"volcengine task {task_id} succeeded but no video_url"
                    )
                usage = r.get("usage") or {}
                return VideoGenResult(
                    task_id=task_id,
                    video_url=video_url,
                    duration_sec=float(r.get("duration") or 0),
                    resolution=r.get("resolution") or "",
                    seed=int(r.get("seed") or 0),
                    has_audio=bool(r.get("generate_audio")),
                    total_tokens=int(usage.get("total_tokens") or 0),
                )
            if status == "failed":
                err = r.get("error") or r
                raise RuntimeError(
                    f"volcengine task {task_id} failed: {err}"
                )
            time.sleep(poll_interval_sec)
        raise TimeoutError(
            f"volcengine task {task_id} did not complete within {timeout_sec}s"
        )

    def download(self, result: VideoGenResult, target_path: Path) -> Path:
        """Download the signed video URL to disk."""
        target_path.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(
            result.video_url,
            headers={"User-Agent": "youtube-clips/0.1"},
        )
        with urllib.request.urlopen(req, timeout=120) as r:
            target_path.write_bytes(r.read())
        return target_path

    # ---- convenience ------------------------------------------------------

    def generate(
        self,
        prompt: str,
        target_path: Path,
        *,
        duration_sec: int = 10,
        resolution: str = "720p",
        run_id: int | None = None,
        shot_idx: int | None = None,
    ) -> VideoGenResult:
        """Synchronous one-shot: create + wait + download. Returns the
        result object for callers that want metadata; the mp4 is at
        `target_path`.

        Logs one cost_event row per successful generation (best-effort).
        """
        from . import cost_log
        t0 = time.monotonic()
        tid = self.create_task(
            prompt, duration_sec=duration_sec, resolution=resolution
        )
        result = self.wait_for_task(tid)
        self.download(result, target_path)
        wall = time.monotonic() - t0
        cost_log.log_doubao_video(
            duration_sec=result.duration_sec or duration_sec,
            resolution=result.resolution or resolution,
            wall_clock_sec=wall,
            model=self.model,
            run_id=run_id,
            shot_idx=shot_idx,
            task_id=result.task_id,
            prompt=prompt,
            total_tokens=result.total_tokens or None,
        )
        return result
