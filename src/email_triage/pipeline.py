"""One triage run: find untriaged inbox mail, classify it, label it."""

import logging
from dataclasses import dataclass, field

from email_triage.config import Config
from email_triage.gmail_client import build_query
from email_triage.models import Email

log = logging.getLogger(__name__)


@dataclass
class RunSummary:
    found: int = 0
    labeled: int = 0
    skipped: int = 0
    failed: int = 0
    results: list[tuple[Email, object]] = field(default_factory=list)


def run_triage(
    gmail, classifier, config: Config, *, dry_run: bool = False, limit: int | None = None
) -> RunSummary:
    summary = RunSummary()
    ids = gmail.list_message_ids(build_query(config), limit or config.max_per_run)
    summary.found = len(ids)
    if not ids:
        log.info("No new messages to triage")
        return summary

    label_ids: dict[str, str] = {}
    if not dry_run:
        # Create the parent label too so Gmail nests the category labels under it.
        label_ids = gmail.ensure_labels([config.label_prefix, *config.all_labels])
    triage_label_ids = {label_ids[name] for name in config.all_labels} if label_ids else set()

    for message_id in ids:
        try:
            email = gmail.get_email(message_id)
            if triage_label_ids.intersection(email.label_ids):
                summary.skipped += 1
                continue
            result = classifier.classify(email)
            summary.results.append((email, result))
            if not dry_run:
                gmail.add_label(message_id, label_ids[config.label_for(result.category)])
                summary.labeled += 1
            log.info(
                "%s %s (%.2f) %r: %s",
                message_id,
                result.category,
                result.confidence,
                email.subject,
                result.reason,
            )
        except Exception:
            summary.failed += 1
            log.exception("Failed to triage message %s; will retry next run", message_id)

    log.info(
        "Run complete%s: found=%d labeled=%d skipped=%d failed=%d",
        " (dry run)" if dry_run else "",
        summary.found,
        summary.labeled,
        summary.skipped,
        summary.failed,
    )
    return summary
