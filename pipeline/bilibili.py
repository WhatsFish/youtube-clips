"""Bilibili web client — fetch video metadata + AI-generated subtitles.

Two-step subtitle path:
  1. `/x/web-interface/view?bvid=BVxxx` — public, no cookies needed.
     Returns video metadata (title, duration, stat, owner, cid).
  2. `/x/player/v2?bvid=BVxxx&cid=NNN` — needs login cookies.
     Returns `data.subtitle.subtitles[]` with subtitle file URLs.
  3. Subtitle JSON file (signed CDN URL) — fetch directly, parse `body[]`
     into [(start, end, text)] tuples.

Cookies live in `~/.config/youtube-clips-bili-cookies.txt` (Netscape
format, as exported by the cookies.txt browser extension). Operator
is in mainland China — Bilibili sessions there last much longer than
YouTube sessions from this Azure VM, so no PO-token-equivalent dance.
"""

from __future__ import annotations

import json
import os
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from http.cookiejar import MozillaCookieJar
from pathlib import Path

DEFAULT_COOKIES = Path.home() / ".config" / "youtube-clips-bili-cookies.txt"
YT_DLP_BIN = str(Path(__file__).resolve().parent.parent / ".venv" / "bin" / "yt-dlp")

UA = (
    "Mozilla/5.0 (X11; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0"
)

_BVID_RE = re.compile(r"BV[A-Za-z0-9]{10}")


def extract_bvid(url_or_id: str) -> str:
    """Accept a full Bilibili URL or a bare BV id, return the BV id."""
    m = _BVID_RE.search(url_or_id)
    if not m:
        raise ValueError(f"could not find BV id in: {url_or_id!r}")
    return m.group(0)


@dataclass(frozen=True)
class BiliVideo:
    bvid: str
    cid: int
    title: str
    desc: str
    duration: int
    owner: str
    stat: dict   # view / like / coin / reply / share / ...
    pubdate: int  # unix ts
    tname: str    # primary category name

    @property
    def url(self) -> str:
        return f"https://www.bilibili.com/video/{self.bvid}"


@dataclass(frozen=True)
class SubtitleLine:
    start: float
    end: float
    text: str


class BilibiliClient:
    def __init__(self, cookies_path: Path | None = None):
        # Cookies are optional for metadata; required for subtitles. We
        # build the cookie jar lazily — `transcript()` is what actually
        # needs auth.
        self.cookies_path = Path(cookies_path) if cookies_path else DEFAULT_COOKIES
        self._opener_with_cookies: urllib.request.OpenerDirector | None = None
        self._opener_plain: urllib.request.OpenerDirector | None = None

    @classmethod
    def from_env(cls) -> "BilibiliClient":
        return cls()

    # ---- HTTP plumbing ----------------------------------------------------

    def _plain_opener(self) -> urllib.request.OpenerDirector:
        if self._opener_plain is None:
            self._opener_plain = urllib.request.build_opener()
        return self._opener_plain

    def _cookies_opener(self) -> urllib.request.OpenerDirector:
        if self._opener_with_cookies is None:
            if not self.cookies_path.exists():
                raise RuntimeError(
                    f"Bilibili cookies file missing at {self.cookies_path}. "
                    f"Export bilibili.com cookies via the cookies.txt browser "
                    f"extension and copy the file there (mode 600)."
                )
            jar = MozillaCookieJar(str(self.cookies_path))
            jar.load(ignore_discard=True, ignore_expires=True)
            self._opener_with_cookies = urllib.request.build_opener(
                urllib.request.HTTPCookieProcessor(jar),
            )
        return self._opener_with_cookies

    def _get_json(self, url: str, *, need_cookies: bool = False) -> dict:
        opener = self._cookies_opener() if need_cookies else self._plain_opener()
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": UA,
                "Referer": "https://www.bilibili.com/",
            },
        )
        with opener.open(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8"))

    # ---- public API -------------------------------------------------------

    def search(
        self,
        keyword: str,
        *,
        max_results: int = 20,
        duration_band: str | None = "3",
        order: str = "click",
    ) -> list[dict]:
        """Bilibili video search. Returns raw API items (lightweight metadata).

        - `duration_band`: '1'(<5min) '2'(5-10) '3'(10-30) '4'(>30); None = any
        - `order`: 'click'(views) 'pubdate' 'totalrank'(relevance) 'dm'(danmaku)
        - Cookies required — Bilibili's web search API silently 412s without them.

        Each item dict keys we care about:
          - bvid, title (HTML-stripped), author, mid, pubdate,
            duration ("MM:SS" string), play (view count),
            video_review (danmaku), description
        """
        params = {
            "keyword": keyword,
            "search_type": "video",
            "order": order,
            "page": "1",
        }
        if duration_band:
            params["duration"] = duration_band
        url = (
            "https://api.bilibili.com/x/web-interface/search/type?"
            + urllib.parse.urlencode(params)
        )
        payload = self._get_json(url, need_cookies=True)
        if payload.get("code") != 0:
            raise RuntimeError(
                f"bilibili search failed: code={payload.get('code')} "
                f"msg={payload.get('message')!r}"
            )
        items = (payload.get("data") or {}).get("result") or []
        # Strip Bilibili's <em class="keyword"> highlight wrappers from
        # the title before returning, otherwise downstream sees XML noise.
        for it in items:
            t = it.get("title") or ""
            it["title"] = re.sub(r"</?em[^>]*>", "", t)
        return items[:max_results]

    def video_info(self, bvid_or_url: str) -> BiliVideo:
        """Fetch the canonical metadata for a video. Public endpoint, no auth."""
        bvid = extract_bvid(bvid_or_url)
        payload = self._get_json(
            f"https://api.bilibili.com/x/web-interface/view?bvid={bvid}",
            need_cookies=False,
        )
        if payload.get("code") != 0:
            raise RuntimeError(
                f"bilibili view API failed for {bvid}: {payload.get('message')}"
            )
        d = payload["data"]
        return BiliVideo(
            bvid=bvid,
            cid=int(d["cid"]),
            title=d["title"],
            desc=(d.get("desc") or "").strip(),
            duration=int(d["duration"]),
            owner=d["owner"]["name"],
            stat=d["stat"],
            pubdate=int(d.get("pubdate") or 0),
            tname=d.get("tname") or "",
        )

    def transcript(self, video: BiliVideo) -> list[SubtitleLine]:
        """Fetch the AI-generated transcript for `video` via yt-dlp.

        Why yt-dlp instead of Bilibili's player/v2 API directly: the API
        path was returning *plausible-looking but wrong* subtitle JSON —
        e.g. a tech-OpenClaw video came back with a transcript about
        BBQ in Jinan. Suspected cause: Bilibili's AI-subtitle CDN serves
        unreliable signed URLs to scraping clients (cache poisoning or
        deliberate anti-scrape). yt-dlp's path (which uses the WBI-signed
        endpoint and a different subtitle resolution flow) returns the
        actual transcript. Verified by spot-check on the 36氪 工资真相
        video. We pay one yt-dlp subprocess per video; metadata is
        still fetched directly above for speed.

        Returns an empty list if no AI/manual subtitle exists.
        """
        import ast
        import subprocess
        # Bilibili's AI subtitles land in info_dict['subtitles'] (not
        # ['automatic_captions'] like YouTube would). yt-dlp also only
        # populates the `data` field of those entries when we explicitly
        # request it via --write-subs + --print "subtitles" — passing
        # -J alone leaves them stub-only with no inline content.
        cmd = [
            YT_DLP_BIN,
            "--cookies", str(self.cookies_path),
            "--skip-download",
            "--write-subs",
            "--sub-langs", "ai-zh,zh-CN,zh-Hans,zh",
            "--sub-format", "srt",
            # Default 20s socket timeout times out on Bilibili's
            # aisubtitle.hdslb.com CDN when reached from Azure Japan
            # (cross-region latency + China CDN throttling).
            "--socket-timeout", "60",
            "--retries", "3",
            "--print", "subtitles",
            video.url,
        ]
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"yt-dlp failed on {video.bvid}: {proc.stderr.strip()[:300]}"
            )
        out = proc.stdout.strip()
        if not out or out == "NA":
            return []
        # `--print "subtitles"` emits a Python repr of the dict (single
        # quotes, etc.) — ast.literal_eval is the safe parse path.
        try:
            subs_dict = ast.literal_eval(out)
        except (ValueError, SyntaxError):
            return []
        if not isinstance(subs_dict, dict):
            return []
        for lang in ("ai-zh", "zh-CN", "zh-Hans", "zh"):
            entries = subs_dict.get(lang) or []
            for entry in entries:
                data = entry.get("data")
                if data:
                    return _parse_srt(data)
                url = entry.get("url")
                if url:
                    req = urllib.request.Request(
                        url, headers={"User-Agent": UA}
                    )
                    with self._plain_opener().open(req, timeout=15) as r:
                        return _parse_srt(r.read().decode("utf-8"))
        return []


def _parse_srt(srt_text: str) -> list[SubtitleLine]:
    """Minimal SRT → SubtitleLine. Bilibili AI subs use comma decimal
    separators (`00:00:01,234`); we also accept `.` defensively."""
    out: list[SubtitleLine] = []
    blocks = srt_text.replace("\r\n", "\n").strip().split("\n\n")
    ts_re = re.compile(
        r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)"
    )
    for block in blocks:
        parts = block.strip().split("\n")
        if len(parts) < 3:
            continue
        m = ts_re.search(parts[1])
        if not m:
            continue
        g = [int(x) for x in m.groups()]
        start = g[0]*3600 + g[1]*60 + g[2] + g[3]/1000
        end = g[4]*3600 + g[5]*60 + g[6] + g[7]/1000
        text = " ".join(p.strip() for p in parts[2:] if p.strip())
        if text:
            out.append(SubtitleLine(start=start, end=end, text=text))
    return out


def format_transcript_lines(lines: list[SubtitleLine]) -> str:
    """Render as `[mm:ss] text` so the agent can refer to specific moments."""
    out = []
    for sl in lines:
        m, s = divmod(int(sl.start), 60)
        out.append(f"[{m:02d}:{s:02d}] {sl.text}")
    return "\n".join(out)
