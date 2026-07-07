import json

import pytest

from email_draft_agent.email_lookup import find_classified_email, payload_email_id, task_run_dirs


def write_payload(path, email_id, subject="Subject"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "basic_information": {
                    "email_id": email_id,
                    "subject": subject,
                    "from": "sender@example.com",
                },
                "email": {
                    "email_id": email_id,
                    "subject": subject,
                    "sender": "sender@example.com",
                    "body": "Body",
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_task_run_dirs_returns_newest_first(tmp_path):
    old_run = tmp_path / "run_2026-06-14_12-11-07__emails_no_emails__task_abc12345"
    new_run = tmp_path / "run_2026-06-14_12-35-42__emails_no_emails__task_abc12345"
    old_run.mkdir()
    new_run.mkdir()

    assert task_run_dirs(tmp_path, "ABC12345") == [new_run, old_run]


def test_find_classified_email_uses_newest_matching_run(tmp_path):
    old_run = tmp_path / "run_2026-06-14_12-11-07__emails_no_emails__task_abc12345"
    new_run = tmp_path / "run_2026-06-14_12-35-42__emails_no_emails__task_abc12345"
    write_payload(old_run / "important" / "123.json", "123", "Old")
    write_payload(new_run / "personal" / "123.json", "123", "New")

    result = find_classified_email(tmp_path, "abc12345", "123")

    assert result.path == new_run / "personal" / "123.json"
    assert result.payload["basic_information"]["subject"] == "New"


def test_find_classified_email_skips_invalid_json(tmp_path, caplog):
    run_dir = tmp_path / "run_2026-06-14_12-35-42__emails_no_emails__task_abc12345"
    bad_path = run_dir / "important" / "bad.json"
    bad_path.parent.mkdir(parents=True, exist_ok=True)
    bad_path.write_text("not json", encoding="utf-8")
    write_payload(run_dir / "personal" / "123.json", "123")

    with caplog.at_level("WARNING", logger="email_draft_agent.email_lookup"):
        result = find_classified_email(tmp_path, "abc12345", "123")

    assert result.path.name == "123.json"
    assert any("Skipping invalid classified email json" in record.getMessage() for record in caplog.records)


def test_find_classified_email_fails_for_missing_task(tmp_path):
    with pytest.raises(RuntimeError, match="No classified email run"):
        find_classified_email(tmp_path, "abc12345", "123")


def test_find_classified_email_fails_for_missing_email(tmp_path):
    run_dir = tmp_path / "run_2026-06-14_12-35-42__emails_no_emails__task_abc12345"
    write_payload(run_dir / "important" / "123.json", "123")

    with pytest.raises(RuntimeError, match="No classified email found"):
        find_classified_email(tmp_path, "abc12345", "999")


def test_payload_email_id_falls_back_to_email_object():
    assert payload_email_id({"email": {"email_id": "456"}}) == "456"
