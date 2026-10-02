"""`triage` command-line entry point."""

import argparse
import logging
import os
import sys
from logging.handlers import RotatingFileHandler

from dotenv import load_dotenv
from openai import OpenAI

from email_triage import launchd
from email_triage.classifier import Classifier
from email_triage.config import load_config
from email_triage.gmail_client import GmailClient, run_oauth_flow
from email_triage.notify import notify
from email_triage.paths import CONFIG_PATH, CREDENTIALS_PATH, ENV_PATH, LOG_DIR, LOG_PATH, TOKEN_PATH
from email_triage.pipeline import run_triage

log = logging.getLogger("email_triage")


def _setup_logging(verbose: bool) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    file_handler = RotatingFileHandler(LOG_PATH, maxBytes=1_000_000, backupCount=3)
    file_handler.setFormatter(fmt)
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    console.setLevel(logging.INFO if verbose else logging.WARNING)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(file_handler)
    root.addHandler(console)
    # Keep third-party chatter (HTTP requests, discovery) out of the log.
    for noisy in ("googleapiclient", "httpx", "httpx2", "openai"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def _cmd_auth(args) -> int:
    run_oauth_flow(CREDENTIALS_PATH, TOKEN_PATH)
    print(f"Authorized. Token saved to {TOKEN_PATH}")
    return 0


def _cmd_run(args) -> int:
    _setup_logging(verbose=args.verbose or args.dry_run)
    try:
        # .env wins over the shell so manual and launchd runs use the same key.
        load_dotenv(ENV_PATH, override=True)
        if not os.environ.get("OPENAI_API_KEY"):
            raise RuntimeError(f"OPENAI_API_KEY is not set (expected in {ENV_PATH})")
        config = load_config(CONFIG_PATH)
        gmail = GmailClient.from_token(TOKEN_PATH)
        classifier = Classifier(OpenAI(timeout=60), config)
        summary = run_triage(gmail, classifier, config, dry_run=args.dry_run, limit=args.limit)
    except Exception as e:
        log.exception("Triage run failed")
        notify(f"Triage run failed: {e}")
        return 1

    if args.dry_run:
        for email, result in summary.results:
            print(f"{result.category:<24} {result.confidence:.2f}  {email.sender[:40]:<40}  {email.subject[:60]}")

    if summary.failed and summary.failed == summary.found - summary.skipped:
        notify(f"All {summary.failed} messages failed to triage. See {LOG_PATH}")
        return 1
    return 0


def _cmd_install(args) -> int:
    path = launchd.install(args.interval)
    print(f"Installed {path}; runs every {args.interval}s. Logs: {LOG_PATH}")
    return 0


def _cmd_uninstall(args) -> int:
    launchd.uninstall()
    print("Schedule removed.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="triage", description="Label Gmail inbox mail by category.")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("auth", help="One-time Google OAuth consent").set_defaults(func=_cmd_auth)

    run = sub.add_parser("run", help="Triage new inbox mail once")
    run.add_argument("--dry-run", action="store_true", help="Classify and print; don't touch Gmail labels")
    run.add_argument("--limit", type=int, help="Max messages this run (overrides config max_per_run)")
    run.add_argument("-v", "--verbose", action="store_true", help="Also log to the console")
    run.set_defaults(func=_cmd_run)

    install = sub.add_parser("install-schedule", help="Run automatically via launchd")
    install.add_argument("--interval", type=int, default=900, help="Seconds between runs (default 900)")
    install.set_defaults(func=_cmd_install)

    sub.add_parser("uninstall-schedule", help="Remove the launchd job").set_defaults(func=_cmd_uninstall)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
