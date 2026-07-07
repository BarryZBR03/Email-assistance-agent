import json
from datetime import datetime

from email_summary_agent.email_classification import ClassificationResult
from email_summary_agent.email_fetcher import EmailRecord
from email_summary_agent.json_storage import (
    classified_email_filename,
    classified_email_path,
    email_time_range,
    run_output_dir,
    sanitize_filename_part,
    write_classified_email,
)


def record(subject="Quarterly Update!"):
    return EmailRecord(
        email_id="123",
        subject=subject,
        sender="boss@example.com",
        date="Sat, 13 Jun 2026 19:45:22 +0000",
        body="Body",
    )


def test_sanitize_filename_part():
    assert sanitize_filename_part("Quarterly Update!", "fallback") == "quarterly_update"
    assert sanitize_filename_part("新设备登录提醒", "fallback") == "新设备登录提醒"
    assert sanitize_filename_part("【安全活动】开通服务手机成功", "fallback") == "安全活动_开通服务手机成功"
    assert sanitize_filename_part("!!!", "fallback") == "fallback"


def test_email_time_range_uses_min_and_max_email_dates():
    emails = [
        EmailRecord("101", "Old", "a@example.com", "Fri, 12 Jun 2026 20:53:12 +0000", "Body"),
        EmailRecord("202", "New", "b@example.com", "Sat, 13 Jun 2026 19:16:41 +0800", "Body"),
    ]

    start, end = email_time_range(emails)

    assert start.strftime("%Y-%m-%d_%H-%M-%S") == "2026-06-12_20-53-12"
    assert end.strftime("%Y-%m-%d_%H-%M-%S") == "2026-06-13_19-16-41"


def test_email_time_range_handles_mixed_timezone_awareness():
    emails = [
        EmailRecord("101", "Naive", "a@example.com", "01 Jul 2026 00:08:21", "Body"),
        EmailRecord("202", "Aware", "b@example.com", "Wed, 1 Jul 2026 12:01:14 +0000", "Body"),
    ]

    start, end = email_time_range(emails)

    assert start.strftime("%Y-%m-%d_%H-%M-%S") == "2026-07-01_00-08-21"
    assert end.strftime("%Y-%m-%d_%H-%M-%S") == "2026-07-01_12-01-14"


def test_email_time_range_returns_none_for_no_parseable_dates():
    assert email_time_range([EmailRecord("303", "No date", "a@example.com", "", "Body")]) is None


def test_run_output_dir_includes_run_time_email_range_and_task_id(tmp_path):
    emails = [
        EmailRecord("101", "Old", "a@example.com", "Fri, 12 Jun 2026 20:53:12 +0000", "Body"),
        EmailRecord("202", "New", "b@example.com", "Sat, 13 Jun 2026 19:16:41 +0800", "Body"),
    ]

    path = run_output_dir(tmp_path, emails, datetime(2026, 6, 13, 21, 45, 10), "ABC-123")

    assert path == tmp_path / "run_2026-06-13_21-45-10__emails_2026-06-12_20-53-12_to_2026-06-13_19-16-41__task_abc_123"


def test_run_output_dir_handles_no_emails(tmp_path):
    path = run_output_dir(tmp_path, [], datetime(2026, 6, 13, 21, 45, 10), "a1b2c3d4")

    assert path == tmp_path / "run_2026-06-13_21-45-10__emails_no_emails__task_a1b2c3d4"


def test_classified_email_filename_uses_subject_and_time():
    assert classified_email_filename(record(), "abc12345") == "123_abc12345_quarterly_update.json"


def test_classified_email_filename_falls_back_for_missing_id_and_subject():
    filename = classified_email_filename(
        EmailRecord(email_id="", subject="", sender="", date="", body=""),
        "ABC-123",
        now=datetime(2026, 6, 13, 20, 1, 2),
    )

    assert filename == "no_email_id_abc_123_no_subject.json"


def test_classified_email_path_uses_sanitized_category_folder(tmp_path):
    classification = ClassificationResult("Work Updates", 0.8, "business")

    path = classified_email_path(record(), classification, tmp_path, "abc12345")

    assert path == tmp_path / "work_updates" / "123_abc12345_quarterly_update.json"


def test_write_classified_email_writes_nested_payload_in_category_folder(tmp_path):
    classification = ClassificationResult("work", 0.8, "business")

    path = write_classified_email(record(), classification, tmp_path, "abc12345")

    assert path == tmp_path / "work" / "123_abc12345_quarterly_update.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["basic_information"] == {
        "email_id": "123",
        "subject": "Quarterly Update!",
        "from": "boss@example.com",
        "date": "Sat, 13 Jun 2026 19:45:22 +0000",
        "category": "work",
        "confidence": 0.8,
        "reason": "business",
    }
    assert payload["email"] == {
        "email_id": "123",
        "subject": "Quarterly Update!",
        "sender": "boss@example.com",
        "date": "Sat, 13 Jun 2026 19:45:22 +0000",
        "body": "Body",
    }
    assert "classification" not in payload


def test_write_classified_email_overwrites_existing_file(tmp_path):
    classification = ClassificationResult("work", 0.8, "business")
    path = write_classified_email(record(), classification, tmp_path, "abc12345")
    path.write_text("old", encoding="utf-8")

    path = write_classified_email(record(), classification, tmp_path, "abc12345")

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["email"]["subject"] == "Quarterly Update!"
    assert "classification" not in payload
    assert payload["basic_information"]["category"] == "work"



def test_write_classified_email_logs_path(caplog, tmp_path):
    classification = ClassificationResult("work", 0.8, "business")

    with caplog.at_level("INFO", logger="email_summary_agent.json_storage"):
        path = write_classified_email(record(), classification, tmp_path, "abc12345")

    messages = [record.getMessage() for record in caplog.records]
    assert any(str(path) in message for message in messages)
    assert any("Wrote classified email file" in message for message in messages)
