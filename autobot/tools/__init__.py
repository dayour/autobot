"""Tool adapters for Power Platform, Dataverse, SharePoint, and Teams.

Each adapter exposes a consistent interface:
    plan(...)   - dry-run preview returning a structured plan
    apply(...)  - execute the operation, returning structured results
"""

from __future__ import annotations

__all__ = [
    "adaptive_cards",
    "pac_cli",
    "dataverse_api",
    "flow_definitions",
    "sharepoint_check",
    "teams_publish",
]
