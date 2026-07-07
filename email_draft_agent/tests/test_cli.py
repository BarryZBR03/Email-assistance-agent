from pathlib import Path

import pytest

from email_draft_agent import cli
from email_draft_agent.config import AppConfig
from email_draft_agent.email_lookup import ClassifiedEmail


def config(tmp_path):
    return AppConfig(
        classified_emails_dir=str(tmp_path / "classified_emails"),
        draft_output_dir=str(tmp_path / "output"),
        llm_provider="openai_compatible",
        llm_api_key="key",
        llm_base_url="https://api.deepseek.com",
        llm_draft_model="deepseek-v4-pro",
        llm_draft_max_concurrency=250,
        email_address="user@example.com",
        smtp_host="smtp.example.com",
        smtp_port=465,
        smtp_auth_code="smtp-secret",
        draft_system_prompt="",
        draft_personality="",
        log_level="INFO",
        draft_log_file="",
    )


def patch_runtime(monkeypatch, tmp_path):
    setup_calls = []
    model_calls = []
    lookup_calls = []

    monkeypatch.setattr(cli, "project_root", lambda: tmp_path)
    monkeypatch.setattr(cli, "load_dotenv", lambda path: None)
    monkeypatch.setattr(cli, "config_from_env", lambda: config(tmp_path))
    monkeypatch.setattr(
        cli,
        "setup_logging",
        lambda log_level, log_file, task_id=None: setup_calls.append((log_level, log_file, task_id)) or "",
    )

    def fake_find_classified_email(classified_dir, task_id, email_id):
        lookup_calls.append((classified_dir, task_id, email_id))
        return ClassifiedEmail(
            path=tmp_path / f"classified_{task_id}_{email_id}.json",
            payload={"basic_information": {"email_id": email_id}, "email": {"body": "Body"}},
        )

    def fake_create_llm_client(provider, api_key, model, base_url):
        model_calls.append((provider, api_key, model, base_url))
        return object()

    monkeypatch.setattr(cli, "find_classified_email", fake_find_classified_email)
    monkeypatch.setattr(cli, "create_llm_client", fake_create_llm_client)
    monkeypatch.setattr(cli, "create_draft_chain", lambda model, system_prompt="", personality="": "chain")
    monkeypatch.setattr(cli, "draft_email", lambda loaded_payload, chain: f"# Draft {loaded_payload['basic_information']['email_id']}")
    return setup_calls, model_calls, lookup_calls


def test_parse_csv_arg_trims_values():
    assert cli.parse_csv_arg(" abc, 123 ,,", "ids") == ["abc", "123"]


def test_parse_csv_arg_rejects_empty_values():
    with pytest.raises(RuntimeError, match="ids"):
        cli.parse_csv_arg(",,", "ids")


def test_expand_task_email_pairs_supports_one_task_many_emails():
    assert cli.expand_task_email_pairs(["task1"], ["email1", "email2"]) == [("task1", "email1"), ("task1", "email2")]


def test_expand_task_email_pairs_supports_equal_length_pairing():
    assert cli.expand_task_email_pairs(["task1", "task2"], ["email1", "email2"]) == [("task1", "email1"), ("task2", "email2")]


def test_expand_task_email_pairs_rejects_mismatched_lists():
    with pytest.raises(RuntimeError, match="same length"):
        cli.expand_task_email_pairs(["task1", "task2"], ["email1", "email2", "email3"])


def test_cli_run_orchestrates_single_email(monkeypatch, tmp_path):
    setup_calls, model_calls, lookup_calls = patch_runtime(monkeypatch, tmp_path)

    output_path = cli.run("abc12345", "123")

    assert setup_calls == [("INFO", "", "abc12345")]
    assert model_calls == [("openai_compatible", "key", "deepseek-v4-pro", "https://api.deepseek.com")]
    assert lookup_calls == [(str(tmp_path / "classified_emails"), "abc12345", "123")]
    assert output_path.endswith("output/task_abc12345/email_draft_abc12345_123.md")
    assert Path(output_path).read_text(encoding="utf-8").endswith("# Draft 123\n")


def test_cli_run_many_orchestrates_one_task_many_emails(monkeypatch, tmp_path):
    setup_calls, model_calls, lookup_calls = patch_runtime(monkeypatch, tmp_path)

    output_paths = cli.run_many(["abc12345"], ["123", "456"])

    assert setup_calls == [("INFO", "", "abc12345")]
    assert model_calls == [("openai_compatible", "key", "deepseek-v4-pro", "https://api.deepseek.com")]
    assert lookup_calls == [
        (str(tmp_path / "classified_emails"), "abc12345", "123"),
        (str(tmp_path / "classified_emails"), "abc12345", "456"),
    ]
    assert output_paths == [
        str(tmp_path / "output" / "task_abc12345" / "email_draft_abc12345_123.md"),
        str(tmp_path / "output" / "task_abc12345" / "email_draft_abc12345_456.md"),
    ]
    assert Path(output_paths[1]).read_text(encoding="utf-8").endswith("# Draft 456\n")


def test_cli_run_many_orchestrates_paired_lists(monkeypatch, tmp_path):
    _, _, lookup_calls = patch_runtime(monkeypatch, tmp_path)

    output_paths = cli.run_many(["task1", "task2"], ["email1", "email2"])

    assert lookup_calls == [
        (str(tmp_path / "classified_emails"), "task1", "email1"),
        (str(tmp_path / "classified_emails"), "task2", "email2"),
    ]
    assert output_paths[0].endswith("output/task_task1/email_draft_task1_email1.md")
    assert output_paths[1].endswith("output/task_task2/email_draft_task2_email2.md")
