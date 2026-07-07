import json

from email_summary_agent.category_json_dump import category_dump_filename, dump_selected_categories


def write_payload(path, category, subject):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "basic_information": {
                    "subject": subject,
                    "from": "sender@example.com",
                    "date": "Sat, 13 Jun 2026 19:45:22 +0000",
                    "category": category,
                    "confidence": 0.9,
                    "reason": "test",
                },
                "email": {
                    "subject": subject,
                    "sender": "sender@example.com",
                    "date": "Sat, 13 Jun 2026 19:45:22 +0000",
                    "body": "Body",
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_category_dump_filename_uses_task_id():
    assert category_dump_filename("ABC-123") == "selected_email_dump_abc_123.json"


def test_dump_selected_categories_combines_selected_categories(tmp_path):
    write_payload(tmp_path / "important" / "a.json", "important", "A")
    write_payload(tmp_path / "work" / "b.json", "work", "B")
    write_payload(tmp_path / "personal" / "c.json", "personal", "C")
    write_payload(tmp_path / "other" / "d.json", "other", "D")
    write_payload(tmp_path / "promotion" / "e.json", "promotion", "E")

    dump_path = dump_selected_categories(tmp_path, "task12345")

    assert dump_path == tmp_path / "selected_email_dump_task12345.json"
    payload = json.loads(dump_path.read_text(encoding="utf-8"))
    assert payload["task_id"] == "task12345"
    assert payload["categories"] == ["important", "other", "personal", "work"]
    assert payload["email_count"] == 4
    assert [email["basic_information"]["subject"] for email in payload["emails"]] == ["A", "D", "C", "B"]
    assert "classification" not in payload["emails"][0]


def test_dump_selected_categories_logs_and_skips_invalid_json(caplog, tmp_path):
    write_payload(tmp_path / "important" / "a.json", "important", "A")
    bad_path = tmp_path / "personal" / "bad.json"
    bad_path.parent.mkdir(parents=True, exist_ok=True)
    bad_path.write_text("not json", encoding="utf-8")

    with caplog.at_level("WARNING", logger="email_summary_agent.category_json_dump"):
        dump_path = dump_selected_categories(tmp_path, "task12345")

    payload = json.loads(dump_path.read_text(encoding="utf-8"))
    assert payload["email_count"] == 1
    assert any("Skipping invalid classified email json" in record.getMessage() for record in caplog.records)
