"""Helpers for locating bundled resource files (icon, etc.).

Lyrebird historically referenced ``icon.png`` with a relative path which only
worked when the process was launched from the project/share directory. These
helpers resolve resources relative to the package location instead so the app
can be started from anywhere.
"""

from pathlib import Path

# app/core/resources.py -> app/core -> app -> project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def resource_path(name: str) -> str:
    """Return the absolute path to a bundled resource as a string."""
    return str(PROJECT_ROOT / name)


def icon_path() -> str:
    """Return the absolute path to the application icon."""
    return resource_path("icon.png")
