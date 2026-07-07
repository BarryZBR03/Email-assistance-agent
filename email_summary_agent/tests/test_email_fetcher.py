from datetime import date
from email.message import EmailMessage

from email_summary_agent.config import config_from_env
from email_summary_agent.email_fetcher import (
    build_search_args,
    email_record_from_bytes,
    fetch_emails,
)


def make_raw_email(subject="Hello", sender="sender@example.com", body="Body text"):
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["Date"] = "Sat, 13 Jun 2026 19:45:22 +0000"
    msg.set_content(body)
    return msg.as_bytes()


def test_build_search_args_unseen_single_sender():
    assert build_search_args(
        "unseen",
        3,
        {"sender@example.com"},
        today=date(2026, 6, 13),
    ) == ["UNSEEN", "SINCE", "11-Jun-2026", "FROM", "sender@example.com"]


def test_build_search_args_all_multiple_senders():
    assert build_search_args(
        "all",
        1,
        {"a@example.com", "b@example.com"},
        today=date(2026, 6, 13),
    ) == ["SINCE", "13-Jun-2026"]


def test_email_record_from_bytes_extracts_fields():
    record = email_record_from_bytes(make_raw_email(subject="Test", body="Hello world"))

    assert record.email_id == ""
    assert record.subject == "Test"
    assert record.sender == "sender@example.com"
    assert record.body == "Hello world"


def test_email_record_from_html_only_email_extracts_readable_text():
    msg = EmailMessage()
    msg["Subject"] = "HTML"
    msg["From"] = "sender@example.com"
    msg["Date"] = "Sat, 13 Jun 2026 19:45:22 +0000"
    msg.set_content(
        "<html><head><style>.x{color:red}</style></head>"
        "<body><h1>Ollama now supports Cline CLI</h1>"
        "<p>Download Ollama &amp; run ollama launch cline.</p></body></html>",
        subtype="html",
    )

    record = email_record_from_bytes(msg.as_bytes())

    assert "Ollama now supports Cline CLI" in record.body
    assert "Download Ollama & run ollama launch cline." in record.body
    assert "<html" not in record.body
    assert "color:red" not in record.body


def test_email_record_prefers_plain_text_over_html():
    msg = EmailMessage()
    msg["Subject"] = "Multipart"
    msg["From"] = "sender@example.com"
    msg["Date"] = "Sat, 13 Jun 2026 19:45:22 +0000"
    msg.set_content("Plain body")
    msg.add_alternative("<html><body><p>HTML body</p></body></html>", subtype="html")

    record = email_record_from_bytes(msg.as_bytes())

    assert record.body == "Plain body"


class FakeImap:
    def __init__(self, host, port):
        self.host = host
        self.port = port

    def login(self, user, auth_code):
        self.user = user
        self.auth_code = auth_code

    def _simple_command(self, command, payload):
        return "OK", [b"ok"]

    def select(self, mailbox):
        return "OK", [b"1"]

    def uid(self, command, *args):
        if command == "SEARCH":
            self.search_args = args
            return "OK", [b"101 202"]
        if command == "FETCH":
            mail_id = args[0]
            sender = b"allowed@example.com" if mail_id == b"101" else b"blocked@example.com"
            raw = make_raw_email(sender=sender.decode())
            return "OK", [(b"RFC822", raw)]
        return "BAD", []

    def logout(self):
        self.logged_out = True


def test_fetch_emails_filters_allowed_senders():
    config = config_from_env(
        {
            "IMAP_HOST": "imap.example.com",
            "IMAP_USER": "user@example.com",
            "IMAP_AUTH_CODE": "secret",
            "ALLOWED_SENDERS": "allowed@example.com",
        }
    )

    records = fetch_emails(config, imap_factory=FakeImap)

    assert len(records) == 1
    assert records[0].email_id == "101"
    assert records[0].sender == "allowed@example.com"



def test_fetch_emails_logs_progress(caplog):
    config = config_from_env(
        {
            "IMAP_HOST": "imap.example.com",
            "IMAP_USER": "user@example.com",
            "IMAP_AUTH_CODE": "secret",
            "ALLOWED_SENDERS": "allowed@example.com",
        }
    )

    with caplog.at_level("INFO", logger="email_summary_agent.email_fetcher"):
        fetch_emails(config, imap_factory=FakeImap)

    messages = [record.getMessage() for record in caplog.records]
    assert any("Connecting to IMAP server imap.example.com:993" in message for message in messages)
    assert any("Mailbox search returned 2 message uids" in message for message in messages)
    assert any("Skipping message" in message for message in messages)
    assert not any("secret" in message for message in messages)
