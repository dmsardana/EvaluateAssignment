"""Fixtures for tools/ CLI integration tests."""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure repo root is importable so `from tools.X` works.
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
