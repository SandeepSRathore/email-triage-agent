"""Install/uninstall the launchd agent that runs `triage run` on an interval."""

import os
import plistlib
import subprocess
import sys
from pathlib import Path

from email_triage.paths import LOG_DIR, PROJECT_DIR

LABEL = "local.email-triage"
PLIST_PATH = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def _domain() -> str:
    return f"gui/{os.getuid()}"


def render_plist(interval_seconds: int) -> dict:
    return {
        "Label": LABEL,
        # The venv's interpreter, so the job doesn't depend on uv or PATH.
        "ProgramArguments": [sys.executable, "-m", "email_triage", "run"],
        "WorkingDirectory": str(PROJECT_DIR),
        "StartInterval": interval_seconds,
        "RunAtLoad": True,
        "StandardOutPath": str(LOG_DIR / "launchd.out.log"),
        "StandardErrorPath": str(LOG_DIR / "launchd.err.log"),
    }


def install(interval_seconds: int) -> Path:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    PLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    uninstall(quiet=True)
    with PLIST_PATH.open("wb") as f:
        plistlib.dump(render_plist(interval_seconds), f)
    subprocess.run(["launchctl", "bootstrap", _domain(), str(PLIST_PATH)], check=True)
    return PLIST_PATH


def uninstall(quiet: bool = False) -> None:
    subprocess.run(
        ["launchctl", "bootout", f"{_domain()}/{LABEL}"],
        check=False,
        capture_output=quiet,
    )
    PLIST_PATH.unlink(missing_ok=True)
