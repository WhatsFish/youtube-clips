"""智谱 BigModel CogVideoX-Flash client.

Mirrors the volcengine.py shape (create + poll + download) but talks to
智谱's BigModel API. CogVideoX-Flash is currently free — operator's
preferred Doubao alternative after Doubao Pro pricing hit budget.

API:
  POST https://open.bigmodel.cn/api/paas/v4/videos/generations
  Body: {model, prompt, quality, with_audio, size, fps, duration}
  → returns id (= task id), task_status: PROCESSING

  GET https://open.bigmodel.cn/api/paas/v4/async-result/{task_id}
  → task_status: SUCCESS | PROCESSING | FAILED
  → video_result[0].url is the mp4 download URL (signed CDN, valid 24h)

Required env: ZHIPU_API_KEY (Bearer token from open.bigmodel.cn).
"""

from __future__ import annotations

import json
import os
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

BIGMODEL_BASE = "https://open.bigmodel.cn/api/paas/v4"

DEFAULT_MODEL = "cogvideox-flash"
# Free tier appears RPM-bounded — generous poll interval avoids
# repeatedly hitting 429 during the ~60-90s typical generation window.
POLL_INTERVAL_SEC = 15
# Free tier free is ~10 min/clip P50 (much slower than Doubao Pro ~60-90s).
# 20 min covers tail latency without making the pipeline indefinitely stall.
DEFAULT_TIMEOUT_SEC = 1200

# Size options supported by CogVideoX-Flash. We always use 16:9
# 1920x1080 for the standard render aspect; other sizes documented for
# future reference.
SIZE_16_9 = "1920x1080"
SIZE_4_3 = "1280x960"
SIZE_9_16 = "1080x1920"
SIZE_1_1 = "1024x1024"


@dataclass(frozen=True)
class VideoGenResult:
    task_id: str
    video_url: str
    duration_sec: float
    resolution: str
    cover_image_url: str | None


class CogVideoXClient:
    def __init__(self, api_key: str | None = None, model: str = DEFAULT_MODEL):
        self.api_key = api_key or os.environ.get("ZHIPU_API_KEY")
        if not self.api_key:
            raise RuntimeError(
                "ZHIPU_API_KEY not set. Register at https://bigmodel.cn/, "
                "create an API key, and add to ~/.config/youtube-clips.env."
            )
        self.model = model

    def _retrying_open(self, req: urllib.request.Request) -> dict:
        """Open the request with 429-aware backoff retry.

        Free tier CogVideoX-Flash has tight rate limits (~RPM-bounded).
        On 429 we back off 30/60/90s and retry up to 3 times — the
        request shape is idempotent on this API so retries are safe.
        """
        delays = [30, 60, 90]
        attempt = 0
        while True:
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    return json.loads(r.read())
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < len(delays):
                    sleep_for = delays[attempt]
                    print(
                        f"  [cogvideox] 429 rate limit; sleeping {sleep_for}s "
                        f"(attempt {attempt + 1}/{len(delays)})",
                        flush=True,
                    )
                    time.sleep(sleep_for)
                    attempt += 1
                    continue
                raise

    def _post(self, path: str, body: dict) -> dict:
        req = urllib.request.Request(
            f"{BIGMODEL_BASE}{path}",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            data=json.dumps(body).encode("utf-8"),
            method="POST",
        )
        return self._retrying_open(req)

    def _get(self, path: str) -> dict:
        req = urllib.request.Request(
            f"{BIGMODEL_BASE}{path}",
            headers={"Authorization": f"Bearer {self.api_key}"},
        )
        return self._retrying_open(req)

    # ---- public API -------------------------------------------------------

    def create_task(
        self,
        prompt: str,
        *,
        duration_sec: int = 5,
        size: str = SIZE_16_9,
        fps: int = 30,
        quality: str = "speed",
        with_audio: bool = False,
    ) -> str:
        """Submit a text-to-video task. Returns the task id.

        CogVideoX-Flash accepts duration in {5, 10}; we coerce.
        """
        # CogVideoX-Flash only takes duration ∈ {5, 10}
        dur = 10 if duration_sec >= 8 else 5
        body = {
            "model": self.model,
            "prompt": prompt,
            "quality": quality,
            "with_audio": with_audio,
            "size": size,
            "fps": fps,
            "duration": dur,
        }
        r = self._post("/videos/generations", body)
        tid = r.get("id")
        if not tid:
            raise RuntimeError(f"cogvideox create_task did not return id: {r}")
        return tid

    def get_task(self, task_id: str) -> dict:
        return self._get(f"/async-result/{task_id}")

    def wait_for_task(
        self,
        task_id: str,
        *,
        timeout_sec: int = DEFAULT_TIMEOUT_SEC,
        poll_interval_sec: int = POLL_INTERVAL_SEC,
    ) -> VideoGenResult:
        """Block until task SUCCESS/FAILED/timeout. Retries transient
        network errors during poll (the task is still running server-side
        even if we momentarily can't read its state)."""
        deadline = time.monotonic() + timeout_sec
        while time.monotonic() < deadline:
            try:
                r = self.get_task(task_id)
            except (urllib.error.URLError, socket.timeout, ConnectionError) as e:
                print(
                    f"  [cogvideox poll] transient error: {type(e).__name__}: {e}; "
                    f"retrying in {poll_interval_sec}s",
                    flush=True,
                )
                time.sleep(poll_interval_sec)
                continue
            status = r.get("task_status")
            if status == "SUCCESS":
                vids = r.get("video_result") or []
                if not vids:
                    raise RuntimeError(f"cogvideox SUCCESS but no video_result: {r}")
                v = vids[0]
                # CogVideoX response doesn't echo the duration we requested,
                # but ffprobe at consume time would catch any mismatch.
                return VideoGenResult(
                    task_id=task_id,
                    video_url=v.get("url"),
                    duration_sec=0.0,  # filled in by ffprobe-time consumer
                    resolution=SIZE_16_9,
                    cover_image_url=v.get("cover_image_url"),
                )
            if status == "FAILED":
                raise RuntimeError(f"cogvideox task FAILED: {r}")
            time.sleep(poll_interval_sec)
        raise TimeoutError(f"cogvideox task {task_id} not done in {timeout_sec}s")

    def download(self, result: VideoGenResult, target_path: Path) -> Path:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(result.video_url, timeout=120) as r:
            data = r.read()
        target_path.write_bytes(data)
        return target_path

    def generate(
        self,
        prompt: str,
        target_path: Path,
        *,
        duration_sec: int = 5,
        resolution: str = "720p",   # accepted for parity with VolcengineClient
        run_id: int | None = None,
        shot_idx: int | None = None,
    ) -> VideoGenResult:
        """Synchronous one-shot: create + wait + download. Returns result.

        Logs one cost_event row (best-effort) — CogVideoX-Flash is free
        so cost_usd is 0, but call count + duration still tracked.
        """
        from . import cost_log
        # Map our resolution string to CogVideoX size enum. 16:9 is the
        # rendering aspect, so all variants land on 1920x1080.
        size = SIZE_16_9
        t0 = time.monotonic()
        tid = self.create_task(
            prompt, duration_sec=duration_sec, size=size,
        )
        result = self.wait_for_task(tid)
        self.download(result, target_path)
        wall = time.monotonic() - t0
        # Best-effort cost log; flash is free so cost_usd=0
        try:
            cost_log.log_event(
                service="youtube-clips-cogvideox",
                provider="zhipu",
                model=self.model,
                cost_usd=0.0,
                duration_ms=int(wall * 1000),
                metadata={
                    "duration_sec": 10 if duration_sec >= 8 else 5,
                    "size": size,
                    "task_id": tid,
                    "run_id": run_id,
                    "shot_idx": shot_idx,
                    "prompt": (prompt or "")[:500],
                },
            )
        except Exception as e:
            print(f"  [cogvideox cost log] {e}")
        return result
