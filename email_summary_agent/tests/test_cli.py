from datetime import datetime
from pathlib import Path

from email_summary_agent import cli
from email_summary_agent.config import AppConfig
from email_summary_agent.email_classification import ClassificationResult
from email_summary_agent.email_fetcher import EmailRecord


class FixedDateTime(datetime):
    @classmethod
    def now(cls):
        return cls(2026, 6, 13, 21, 45, 10)


def test_cli_run_orchestrates(monkeypatch, tmp_path):
    config = AppConfig(
        imap_host="imap.example.com",
        imap_user="user@example.com",
        imap_auth_code="secret",
        imap_port=993,
        email_status="unseen",
        recent_days=1,
        allowed_senders=frozenset(),
        categories=("work", "other"),
        output_dir=str(tmp_path),
        llm_provider="openai_compatible",
        llm_api_key="key",
        llm_base_url="https://api.deepseek.com",
        llm_classification_model="deepseek-v4-flash",
        llm_summary_model="deepseek-v4-pro",
        llm_classification_max_concurrency=1000,
        summary_system_prompt="",
        log_level="INFO",
        log_file="",
    )
    email_record = EmailRecord(
        "123",
        "Subject",
        "from@example.com",
        "Sat, 13 Jun 2026 19:45:22 +0000",
        "Body",
    )
    write_calls = []

    def fake_write(email_record, classification, output_dir, task_id):
        write_calls.append((output_dir, task_id))
        return output_dir / "work" / "123_abc12345_subject.json"

    monkeypatch.setattr(cli, "datetime", FixedDateTime)
    monkeypatch.setattr(cli, "uuid4", lambda: type("FakeUuid", (), {"hex": "abc12345deadbeef"})())
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)
    monkeypatch.setattr(cli, "config_from_env", lambda: config)
    setup_calls = []
    monkeypatch.setattr(
        cli,
        "setup_logging",
        lambda log_level, log_file, task_id=None: setup_calls.append((log_level, log_file, task_id)) or "logs/task_abc12345/email_summary_agent.log",
    )
    model_calls = []

    def fake_create_llm_client(provider, api_key, model, base_url):
        model_calls.append((provider, api_key, model, base_url))
        return object()

    monkeypatch.setattr(cli, "create_llm_client", fake_create_llm_client)
    monkeypatch.setattr(cli, "create_classification_chain", lambda model: object())
    monkeypatch.setattr(cli, "fetch_emails", lambda loaded_config: [email_record])
    monkeypatch.setattr(
        cli,
        "classify_email",
        lambda email_record, categories, chain: ClassificationResult("work", 1.0, "ok"),
    )
    monkeypatch.setattr(cli, "write_classified_email", fake_write)
    dump_calls = []
    summary_calls = []

    def fake_dump_selected_categories(output_dir, task_id):
        dump_calls.append((output_dir, task_id))
        return output_dir / f"selected_email_dump_{task_id}.json"

    def fake_summarize_selected_email_dump(dump_path, output_dir, task_id, chain):
        summary_calls.append((dump_path, output_dir, task_id, chain))
        return output_dir / f"email_summary_{task_id}.md"

    monkeypatch.setattr(cli, "dump_selected_categories", fake_dump_selected_categories)
    monkeypatch.setattr(cli, "create_summary_chain", lambda model, system_prompt="": "summary-chain")
    monkeypatch.setattr(cli, "summarize_selected_email_dump", fake_summarize_selected_email_dump)

    output_paths = cli.run()

    expected_run_dir = tmp_path / "run_2026-06-13_21-45-10__emails_2026-06-13_19-45-22_to_2026-06-13_19-45-22__task_abc12345"
    assert setup_calls == [("INFO", "", "abc12345")]
    assert write_calls == [(expected_run_dir, "abc12345")]
    assert dump_calls == [(expected_run_dir, "abc12345")]
    assert summary_calls == [
        (
            expected_run_dir / "selected_email_dump_abc12345.json",
            Path("output") / "task_abc12345",
            "abc12345",
            "summary-chain",
        )
    ]
    assert model_calls == [
        ("openai_compatible", "key", "deepseek-v4-flash", "https://api.deepseek.com"),
        ("openai_compatible", "key", "deepseek-v4-pro", "https://api.deepseek.com"),
    ]
    assert len(output_paths) == 3
    assert output_paths[0].endswith("123_abc12345_subject.json")
    assert output_paths[1].endswith("selected_email_dump_abc12345.json")
    assert output_paths[2].endswith("output/task_abc12345/email_summary_abc12345.md")
