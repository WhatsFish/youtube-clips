"""Prompt loader.

Prompts live as plain markdown files under `<project>/prompts/<task>.v<n>.md`
with YAML frontmatter holding `name`, `version`, etc. The body uses
`str.format()` placeholders that the caller fills in at render time.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROMPTS_DIR = PROJECT_ROOT / "prompts"

_FRONTMATTER_RE = re.compile(
    r"\A---\s*\n(.*?)\n---\s*\n(.*)\Z", re.DOTALL
)


@dataclass(frozen=True)
class Prompt:
    name: str
    version: int
    body: str
    metadata: dict[str, Any]
    source_path: Path

    @property
    def stamp(self) -> str:
        """The string to record in output artifacts so we can trace back
        which prompt produced what.
        """
        return f"{self.name}.v{self.version}"

    def render(self, **values: Any) -> str:
        """Fill in placeholders. Missing keys raise KeyError; extra keys
        are silently allowed.
        """
        return self.body.format(**values)


def load_prompt(name: str, version: int | str = "latest") -> Prompt:
    """Load `<name>.v<version>.md`. `version="latest"` picks the highest
    `vN` file matching the name."""
    if version == "latest":
        candidates = sorted(
            PROMPTS_DIR.glob(f"{name}.v*.md"),
            key=lambda p: int(re.search(r"\.v(\d+)\.md$", p.name).group(1)),
        )
        if not candidates:
            raise FileNotFoundError(
                f"no prompt files matching {name}.v*.md in {PROMPTS_DIR}"
            )
        path = candidates[-1]
    else:
        path = PROMPTS_DIR / f"{name}.v{version}.md"
        if not path.exists():
            raise FileNotFoundError(f"prompt not found: {path}")

    raw = path.read_text(encoding="utf-8")
    m = _FRONTMATTER_RE.match(raw)
    if not m:
        raise ValueError(
            f"prompt {path} is missing YAML frontmatter (--- ... ---)"
        )
    meta = yaml.safe_load(m.group(1)) or {}
    body = m.group(2)

    file_version = int(re.search(r"\.v(\d+)\.md$", path.name).group(1))
    if "version" in meta and int(meta["version"]) != file_version:
        raise ValueError(
            f"version mismatch in {path}: filename says v{file_version} "
            f"but frontmatter says v{meta['version']}"
        )

    return Prompt(
        name=meta.get("name", name),
        version=file_version,
        body=body,
        metadata=meta,
        source_path=path,
    )
