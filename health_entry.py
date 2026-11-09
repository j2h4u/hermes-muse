"""Health pre-run gate: wake a wording agent only when the diagnostic alert set changed."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from hermes_muse.health import run

if __name__ == "__main__":
    text = run(MUSE_HOME)  # noqa: F821 - injected by the launcher
    if text:
        print(text)
    else:
        print(json.dumps({"wakeAgent": False, "reason": "health unchanged"}))
