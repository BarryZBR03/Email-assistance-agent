from email_draft_agent.draft_output import draft_markdown_filename, write_draft_markdown


def test_draft_markdown_filename_uses_task_and_email_id():
    assert draft_markdown_filename("ABC-123", "Email 456!") == "email_draft_abc_123_email_456.md"


def test_write_draft_markdown_writes_task_output(tmp_path):
    path = write_draft_markdown(
        tmp_path,
        "ABC-123",
        "456",
        "classified/path.json",
        "To: sender@example.com\n\nSubject: Re: Test\n\nBody:\nHello",
    )

    assert path == tmp_path / "task_abc_123" / "email_draft_abc_123_456.md"
    assert path.read_text(encoding="utf-8") == (
        "Task ID: ABC-123\n"
        "Email ID: 456\n"
        "Source: classified/path.json\n\n"
        "To: sender@example.com\n\n"
        "Subject: Re: Test\n\n"
        "Body:\n"
        "Hello\n"
    )
