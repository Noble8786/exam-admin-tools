"""
Shared utility functions for the multi-feature app.
Add common helpers here as the project grows.
"""

from pathlib import Path


def ensure_dir(path: str | Path) -> Path:
    """Create directory if it does not exist and return the Path object."""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p
