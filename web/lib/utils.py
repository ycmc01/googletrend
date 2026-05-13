"""Shared utilities for Streamlit pages."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
GITS_CLI = PROJECT_ROOT / "scripts" / "gits.py"


def run_cli(*args: str, show_output: bool = True) -> tuple[int, str, str]:
    """Run a gits CLI subcommand. Returns (returncode, stdout, stderr)."""
    cmd = [sys.executable, str(GITS_CLI), *args]
    if show_output:
        st.code(" ".join(cmd), language="bash")
    result = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return result.returncode, result.stdout, result.stderr


def header(title: str, emoji: str = "") -> None:
    st.set_page_config(page_title=f"GITS — {title}", page_icon=emoji or "📈", layout="wide")
    st.title(f"{emoji} {title}".strip())
