# prompts

LLM prompts that drive the pipeline live here as plain markdown files,
one file per (task, version). The intent is that **prompt iteration
should never require a code change** — diff a `.md`, commit, re-run.

## Naming

```
<task>.v<n>.md
```

- `task` is a stable slug for what the prompt does (`edl-continuous`,
  `topic-generation`, `source-filter`, ...).
- `v<n>` is a monotonic version. Don't edit a frozen version in place;
  if you need to iterate, copy it to the next version. Old versions
  stay around so you can A/B against them and so EDL outputs that
  reference them remain interpretable.

## File shape

Each prompt is YAML frontmatter followed by the prompt body. The body
is consumed by `str.format(**kwargs)` so any `{name}` token gets
substituted at runtime; if you need a literal `{` or `}` in the body,
double them (`{{`, `}}`).

```markdown
---
name: edl-continuous
version: 2
purpose: 从英文字幕生成连续中文解说 EDL
last_updated: 2026-05-09
notes: |
  v1: clip + narration_after; abandoned (visual stutter)
  v2: continuous narration with source as B-roll
---

[prompt body — any {placeholder} here gets substituted]
```

The loader is `pipeline.prompts.load_prompt("edl-continuous", version=2)`
which returns a `Prompt` object exposing `body`, `version`, `name`,
and `metadata`.

## Versioning convention

When you produce output (e.g., write `edl.json`), stamp the prompt's
identity (`prompt_template_version: "edl-continuous.v2"`) so we can
trace back: which exact prompt + which exact Profile produced this
EDL? `git log prompts/<file>` plus the EDL stamp is enough to reconstruct.

## Current prompts

- `edl-continuous.v3.md` — current default. Domain-neutral version of
  v2 — `channel_position` / `tone_description` / `verbal_tics_example` /
  `forbidden_phrases_block` / `disclaimer_requirement` are placeholders
  fed from the active Profile, so different Profiles produce visibly
  different style without prompt edits.
- `edl-continuous.v2.md` — kept as fallback. Tech-flavored verbal_tics
  + "Bilibili 科技频道 UP 主" hardcoded in body; works for tech-insights-cn
  but not other Profiles. Pass `--prompt-version 2` if you want to A/B.
- `source-pick.v1.md` — used by `scripts/discover-source.py` for the
  metadata-based source picker. Not affected by the v2→v3 evolution.
