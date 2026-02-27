"""Conftest for CS Builder tests — avoids loading the root conftest's dependencies."""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure autobot is importable
root_dir = Path(__file__).resolve().parent.parent.parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))
