"""Entry point for the gits CLI: `python scripts/gits.py <command> ...`."""
import sys
from pathlib import Path

# Force UTF-8 stdout on Windows so rich can emit em-dashes, arrows etc.
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from gits.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
