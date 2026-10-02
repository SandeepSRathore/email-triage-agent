from types import SimpleNamespace

import pytest

from email_triage.classifier import MAX_BODY_CHARS, ClassificationError, Classifier
from email_triage.config import Config
from email_triage.models import Email

CONFIG = Config(
    model="test-model",
    categories=[
        {"name": "Urgent", "description": "needs action today"},
        {"name": "Promotions", "description": "marketing"},
    ],
)

EMAIL = Email(
    id="m1",
    sender="Shop <deals@shop.com>",
    subject="50% off",
    date="Thu, 1 Oct 2026",
    body="Big sale",
    list_unsubscribe="<mailto:u@shop.com>",
)


class FakeCompletions:
    def __init__(self, parsed=None, refusal=None):
        self.calls = []
        self._message = SimpleNamespace(parsed=parsed, refusal=refusal)

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=self._message)])


def fake_client(completions):
    return SimpleNamespace(chat=SimpleNamespace(completions=completions))


def make_result(classifier, category):
    return classifier.response_model(category=category, confidence=0.9, reason="r")


def test_returns_parsed_classification_and_builds_prompt():
    completions = FakeCompletions()
    classifier = Classifier(fake_client(completions), CONFIG)
    completions._message.parsed = make_result(classifier, "Promotions")

    result = classifier.classify(EMAIL)

    assert result.category == "Promotions"
    call = completions.calls[0]
    assert call["model"] == "test-model"
    assert call["response_format"] is classifier.response_model
    system, user = call["messages"]
    assert "Urgent: needs action today" in system["content"]
    assert "Promotions: marketing" in system["content"]
    assert "deals@shop.com" in user["content"]
    assert "50% off" in user["content"]
    assert "List-Unsubscribe: present" in user["content"]


def test_response_model_restricts_category_to_config():
    classifier = Classifier(fake_client(FakeCompletions()), CONFIG)
    with pytest.raises(ValueError):
        make_result(classifier, "Spam")


def test_truncates_long_bodies():
    completions = FakeCompletions()
    classifier = Classifier(fake_client(completions), CONFIG)
    completions._message.parsed = make_result(classifier, "Urgent")
    long_email = Email(id="m2", sender="s", subject="s", date="d", body="x" * 50_000)

    classifier.classify(long_email)

    user = completions.calls[0]["messages"][1]["content"]
    assert "x" * MAX_BODY_CHARS in user
    assert "x" * (MAX_BODY_CHARS + 1) not in user


def test_refusal_raises():
    completions = FakeCompletions(refusal="I can't help with that")
    classifier = Classifier(fake_client(completions), CONFIG)
    with pytest.raises(ClassificationError, match="refused"):
        classifier.classify(EMAIL)
