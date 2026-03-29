"""
Pytest configuration.

Ensures the project root (devflow/ package) stays at sys.path[0] so the
devflow package always takes precedence over lib/devflow.py, regardless
of which test file is collected first.
"""
import sys
from pathlib import Path

_PROJECT_ROOT = str(Path(__file__).parent.parent)


def pytest_collection_modifyitems(session, config, items):
    """Re-anchor the project root after all test modules are imported."""
    if _PROJECT_ROOT in sys.path:
        sys.path.remove(_PROJECT_ROOT)
    sys.path.insert(0, _PROJECT_ROOT)
