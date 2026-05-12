"""智谱 BigModel CogView-3-Flash client.

Image-tier counterpart to cogvideox.py. CogView-3-Flash is currently free
and **dramatically faster** than CogVideoX-Flash (~5-10s per image vs
~10 minutes per video). For B-roll under continuous Chinese narration,
a single AI-generated still with ffmpeg ken-burns (slow zoom/pan)
animation is visually equivalent to a short AI video clip — viewers'
eyes are on the subtitle band, not pixel-level motion.

API:
  POST https://open.bigmodel.cn/api/paas/v4/images/generations
  Body: {model, prompt, size}
  → returns synchronously: data[0].url (signed PNG, 24h)

Size constraint: each dim 512-2880 px, divisible by 16, total pixels
≤ 2^21 (2,097,152). 1280x720 fits cleanly for 16:9 output.

Required env: ZHIPU_API_KEY (same key as cogvideox).
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
DEFAULT_MODEL = "cogview-3-flash"
DEFAULT_SIZE = "1280x720"


@dataclass(frozen=True)
class ImageGenResult:
    image_id: str
    image_url: str
    size: str


class CogViewClient:
    def __init__(self, api_key: str | None = None, model: str = DEFAULT_MODEL):
        self.api_key = api_key or os.environ.get("ZHIPU_API_KEY")
        if not self.api_key:
            raise RuntimeError(
                "ZHIPU_API_KEY not set. Register at https://bigmodel.cn/, "
                "create an API key, add to ~/.config/youtube-clips.env."
            )
        self.model = model

    def _post(self, path: str, body: dict, *, retries: int = 3) -> dict:
        """POST with 429-aware backoff (CogView free tier is rate-limited)."""
        delays = [10, 30, 60]
        attempt = 0
        while True:
            req = urllib.request.Request(
                f"{BIGMODEL_BASE}{path}",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                data=json.dumps(body).encode("utf-8"),
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=30) as r:
                    return json.loads(r.read())
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < len(delays):
                    sleep_for = delays[attempt]
                    print(
                        f"  [cogview] 429 rate limit; sleeping {sleep_for}s "
                        f"(attempt {attempt + 1}/{len(delays)})",
                        flush=True,
                    )
                    time.sleep(sleep_for)
                    attempt += 1
                    continue
                raise

    def generate(self, prompt: str, *, size: str = DEFAULT_SIZE) -> ImageGenResult:
        """Submit a text-to-image request. CogView returns synchronously
        (unlike CogVideoX which is async-task-based). Single round trip,
        ~5-10s typical."""
        r = self._post(
            "/images/generations",
            {"model": self.model, "prompt": prompt, "size": size},
        )
        data = r.get("data") or []
        if not data or not data[0].get("url"):
            raise RuntimeError(f"cogview returned no image url: {r}")
        return ImageGenResult(
            image_id=r.get("id") or "",
            image_url=data[0]["url"],
            size=size,
        )

    def download(self, result: ImageGenResult, target_path: Path) -> Path:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(result.image_url, timeout=60) as r:
            data = r.read()
        target_path.write_bytes(data)
        return target_path
