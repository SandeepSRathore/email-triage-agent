import base64

from email_triage.config import Config
from email_triage.gmail_client import build_query, parse_message


def b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode()


def make_config(**overrides) -> Config:
    return Config(
        categories=[
            {"name": "Urgent", "description": "u"},
            {"name": "Needs-Reply", "description": "n"},
        ],
        **overrides,
    )


def test_build_query_excludes_already_triaged():
    query = build_query(make_config(lookback_days=3))
    assert query == (
        "in:inbox newer_than:3d -label:triage-urgent -label:triage-needs-reply"
    )


def headers(**kv):
    return [{"name": k.replace("_", "-"), "value": v} for k, v in kv.items()]


def test_parse_prefers_plain_text_part():
    raw = {
        "id": "m1",
        "labelIds": ["INBOX", "UNREAD"],
        "snippet": "snip",
        "payload": {
            "mimeType": "multipart/alternative",
            "headers": headers(From="a@x.com", Subject="Hi", Date="Thu, 1 Oct 2026"),
            "parts": [
                {"mimeType": "text/plain", "body": {"data": b64("plain body")}},
                {"mimeType": "text/html", "body": {"data": b64("<p>html body</p>")}},
            ],
        },
    }
    email = parse_message(raw)
    assert email.id == "m1"
    assert email.sender == "a@x.com"
    assert email.subject == "Hi"
    assert email.date == "Thu, 1 Oct 2026"
    assert email.body == "plain body"
    assert email.label_ids == ["INBOX", "UNREAD"]
    assert email.list_unsubscribe is None


def test_parse_falls_back_to_stripped_html_in_nested_parts():
    raw = {
        "id": "m2",
        "payload": {
            "mimeType": "multipart/mixed",
            "headers": headers(From="b@x.com", Subject="S", List_Unsubscribe="<mailto:u@x.com>"),
            "parts": [
                {
                    "mimeType": "multipart/related",
                    "parts": [
                        {
                            "mimeType": "text/html",
                            "body": {
                                "data": b64(
                                    "<html><style>p{}</style><p>Hello&nbsp;<b>world</b></p></html>"
                                )
                            },
                        }
                    ],
                },
                {"mimeType": "application/pdf", "filename": "a.pdf", "body": {"attachmentId": "x"}},
            ],
        },
    }
    email = parse_message(raw)
    assert email.body == "Hello world"
    assert email.list_unsubscribe == "<mailto:u@x.com>"
    assert email.label_ids == []


def test_parse_single_part_body_and_missing_headers():
    raw = {
        "id": "m3",
        "snippet": "fallback snippet",
        "payload": {"mimeType": "text/plain", "headers": [], "body": {"size": 0}},
    }
    email = parse_message(raw)
    assert email.sender == ""
    assert email.subject == ""
    assert email.body == "fallback snippet"
