"""Atomic capability tools — usable from scripts directly AND exposed
to Claude as an MCP server (see `pipeline.mcp_server`).

Each tool is a pure function with:
  - Clear input args (type-hinted; MCP derives JSON schema from these)
  - JSON-serialisable return (dict / list of dicts / str)
  - Best-effort error handling (return {"error": "..."} on failure
    instead of raising; agents handle errors better as data)

This module is the canonical interface. `pipeline/bilibili.py`,
`pipeline/pexels.py` etc remain the implementation; tools here are thin
wrappers + light schema massaging.
"""
