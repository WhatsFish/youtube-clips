"""Background-music library lookup.

Operator drops audio tracks (mp3/m4a/wav/ogg/flac) into
`/video/youtube-clips/bgm/<mood>/`. The renderer asks for a track
matching a mood tag chosen by the EDL agent. We pick one at random from
the mood folder (deterministic-per-render is overkill — the operator can
re-render to roll the dice if they don't like a pick) and return its
path; if the folder is empty or missing, return None and the renderer
silently degrades to no BGM.

Mood folders we expect (matched against the prompt's allowed list):
  upbeat / calm / tense / neutral

Adding a new mood = create the directory + update the prompt's vocab
list. No code change here; the lookup is just a file glob.
"""

from __future__ import annotations

import random
from pathlib import Path

BGM_BASE = Path("/video/youtube-clips/bgm")
SUPPORTED_EXT = {".mp3", ".m4a", ".wav", ".ogg", ".flac", ".opus"}


def pick_track(mood: str, *, seed: str | None = None) -> Path | None:
    """Return a random track from `bgm/<mood>/` or None if no match."""
    folder = BGM_BASE / mood
    if not folder.is_dir():
        return None
    candidates = sorted(
        p for p in folder.iterdir()
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXT
    )
    if not candidates:
        return None
    rng = random.Random(seed) if seed else random
    return rng.choice(candidates)
