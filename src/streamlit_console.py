"""Streamlit launch script for the V6 agent console.

This thin launcher exists to bootstrap ``sys.path``. Streamlit runs the target
file as a top-level module, so the real console in
``carbon_agent/streamlit_app.py`` cannot be launched directly: it uses
package-relative imports that raise ``ImportError`` without a parent package.

Running this file puts ``src/`` on ``sys.path``, which lets the absolute import
below resolve and keeps ``pip install -e .`` optional for console users.
"""

from __future__ import annotations

import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from carbon_agent.streamlit_app import main

if __name__ == "__main__":
    main()
