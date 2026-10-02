import subprocess


def notify(message: str, title: str = "Email triage") -> None:
    """Show a macOS notification. Best effort: never raises."""
    # Pass text as argv so quotes in the message can't break the AppleScript.
    script = ["-e", "on run argv", "-e", "display notification (item 1 of argv) with title (item 2 of argv)", "-e", "end run"]
    try:
        subprocess.run(["osascript", *script, message, title], check=False, timeout=10, capture_output=True)
    except (OSError, subprocess.SubprocessError):
        pass
