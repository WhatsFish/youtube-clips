#!/usr/bin/env python3
"""Thin wrapper: producer Phase 1 only (outline + script).

After Stage 2 the pipeline INSERTs a draft job with status='script_draft'
and stops. Operator reviews the script on the web at
  /youtube-clips/jobs/<slug>/review
and clicks approve, which triggers Phase 2 (produce-render.py) async.

Usage:
  source ~/.config/youtube-clips.env
  .venv/bin/python scripts/produce-script.py \\
      --topic "..." --profile shanyang-cn

All other flags are passed through to produce-original.py.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
os.execv(
    sys.executable,
    [
        sys.executable,
        os.path.join(HERE, "produce-original.py"),
        "--stage", "script",
        *sys.argv[1:],
    ],
)
