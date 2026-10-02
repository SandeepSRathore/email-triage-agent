from types import SimpleNamespace

from email_triage.config import Config
from email_triage.models import Email
from email_triage.pipeline import run_triage

CONFIG = Config(
    max_per_run=5,
    categories=[
        {"name": "Urgent", "description": "u"},
        {"name": "FYI", "description": "f"},
    ],
)


def email(id, subject="s", label_ids=()):
    return Email(id=id, sender="a@x.com", subject=subject, date="d", body="b", label_ids=list(label_ids))


class FakeGmail:
    def __init__(self, emails):
        self.emails = {e.id: e for e in emails}
        self.list_calls = []
        self.ensured = []
        self.added = []

    def list_message_ids(self, query, max_results):
        self.list_calls.append((query, max_results))
        return list(self.emails)[:max_results]

    def get_email(self, message_id):
        return self.emails[message_id]

    def ensure_labels(self, names):
        self.ensured.append(names)
        return {name: f"id:{name}" for name in names}

    def add_label(self, message_id, label_id):
        self.added.append((message_id, label_id))


class FakeClassifier:
    def __init__(self, by_subject, fail_on=()):
        self.by_subject = by_subject
        self.fail_on = set(fail_on)

    def classify(self, email):
        if email.id in self.fail_on:
            raise RuntimeError("boom")
        return SimpleNamespace(category=self.by_subject[email.subject], confidence=0.8, reason="r")


def test_labels_each_email_with_its_category():
    gmail = FakeGmail([email("1", "a"), email("2", "b")])
    classifier = FakeClassifier({"a": "Urgent", "b": "FYI"})

    summary = run_triage(gmail, classifier, CONFIG)

    assert gmail.ensured == [["Triage", "Triage/Urgent", "Triage/FYI"]]
    assert gmail.added == [("1", "id:Triage/Urgent"), ("2", "id:Triage/FYI")]
    assert (summary.found, summary.labeled, summary.failed) == (2, 2, 0)


def test_failure_on_one_email_does_not_stop_the_rest():
    gmail = FakeGmail([email("1", "a"), email("2", "b")])
    classifier = FakeClassifier({"a": "Urgent", "b": "FYI"}, fail_on={"1"})

    summary = run_triage(gmail, classifier, CONFIG)

    assert gmail.added == [("2", "id:Triage/FYI")]
    assert (summary.labeled, summary.failed) == (1, 1)


def test_dry_run_changes_nothing_in_gmail():
    gmail = FakeGmail([email("1", "a")])

    summary = run_triage(gmail, FakeClassifier({"a": "Urgent"}), CONFIG, dry_run=True)

    assert gmail.ensured == []
    assert gmail.added == []
    assert summary.labeled == 0
    assert [(e.id, c.category) for e, c in summary.results] == [("1", "Urgent")]


def test_respects_max_per_run_and_limit_override():
    gmail = FakeGmail([email(str(i), "a") for i in range(10)])
    classifier = FakeClassifier({"a": "FYI"})

    run_triage(gmail, classifier, CONFIG)
    run_triage(gmail, classifier, CONFIG, limit=2)

    assert [m for _, m in gmail.list_calls] == [5, 2]


def test_skips_emails_that_already_have_a_triage_label():
    # Guards idempotency even if the search query fails to exclude them.
    gmail = FakeGmail([email("1", "a", label_ids=["INBOX", "id:Triage/FYI"]), email("2", "a")])

    summary = run_triage(gmail, FakeClassifier({"a": "Urgent"}), CONFIG)

    assert gmail.added == [("2", "id:Triage/Urgent")]
    assert summary.skipped == 1


def test_no_messages_makes_no_label_calls():
    gmail = FakeGmail([])

    summary = run_triage(gmail, FakeClassifier({}), CONFIG)

    assert gmail.ensured == []
    assert summary.found == 0
