import pytest

from email_draft_agent.config import AppConfig
from email_draft_agent.email_sender import parse_draft_markdown, send_draft_email


def config(port=465):
    return AppConfig(
        classified_emails_dir="classified_emails",
        draft_output_dir="output",
        llm_provider="openai_compatible",
        llm_api_key="key",
        llm_base_url="https://api.deepseek.com",
        llm_draft_model="deepseek-v4-pro",
        llm_draft_max_concurrency=250,
        email_address="user@example.com",
        smtp_host="smtp.example.com",
        smtp_port=port,
        smtp_auth_code="smtp-secret",
        draft_system_prompt="",
        draft_personality="",
        log_level="INFO",
        draft_log_file="",
    )


class FakeServer:
    instances = []

    def __init__(self, host, port, timeout):
        self.host = host
        self.port = port
        self.timeout = timeout
        self.started_tls = False
        self.login_call = None
        self.sent_message = None
        FakeServer.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def starttls(self):
        self.started_tls = True

    def login(self, user, password):
        self.login_call = (user, password)

    def send_message(self, message):
        self.sent_message = message


def test_parse_draft_markdown_reads_headers_after_metadata():
    parsed = parse_draft_markdown(
        "Task ID: abc\nEmail ID: 123\n\nTo: sender@example.com\nSubject: Re: Test\nBody:\nHello\nThanks"
    )

    assert parsed.recipient == "sender@example.com"
    assert parsed.subject == "Re: Test"
    assert parsed.body == "Hello\nThanks"


@pytest.mark.parametrize("markdown, message", [
    ("Subject: Re: Test\nBody:\nHello", "To"),
    ("To: sender@example.com\nBody:\nHello", "Subject"),
    ("To: sender@example.com\nSubject: Re: Test", "Body"),
])
def test_parse_draft_markdown_rejects_missing_send_fields(markdown, message):
    with pytest.raises(RuntimeError, match=message):
        parse_draft_markdown(markdown)


def test_send_draft_email_uses_smtp_ssl_for_port_465(monkeypatch):
    FakeServer.instances = []
    monkeypatch.setattr("email_draft_agent.email_sender.smtplib.SMTP_SSL", FakeServer)

    sent = send_draft_email(config(465), "To: sender@example.com\nSubject: Re: Test\nBody:\nHello")

    server = FakeServer.instances[0]
    assert sent.recipient == "sender@example.com"
    assert server.started_tls is False
    assert server.login_call == ("user@example.com", "smtp-secret")
    assert server.sent_message["To"] == "sender@example.com"
    assert server.sent_message["Subject"] == "Re: Test"


def test_send_draft_email_uses_starttls_for_non_ssl_port(monkeypatch):
    FakeServer.instances = []
    monkeypatch.setattr("email_draft_agent.email_sender.smtplib.SMTP", FakeServer)

    send_draft_email(config(587), "To: sender@example.com\nSubject: Re: Test\nBody:\nHello")

    assert FakeServer.instances[0].started_tls is True


def test_send_draft_email_rejects_missing_smtp_config():
    bad_config = config()
    bad_config = AppConfig(**{**bad_config.__dict__, "smtp_host": ""})

    with pytest.raises(RuntimeError, match="SMTP_HOST"):
        send_draft_email(bad_config, "To: sender@example.com\nSubject: Re: Test\nBody:\nHello")
