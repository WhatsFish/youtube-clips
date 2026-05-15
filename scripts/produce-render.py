#!/usr/bin/env python3
"""Thin wrapper: producer Phase 2 only (acquire assets → render → publish).

Resumes from an existing draft job (status='script_draft' or 'rejected').
Invoked by the web approve handler after the operator reviews the script.

Usage:
  source ~/.config/youtube-clips.env
  .venv/bin/python scripts/produce-render.py --job-id 42

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
        "--stage", "render",
        *sys.argv[1:],
    ],
)
