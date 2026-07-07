import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
sys.path.insert(0, str(BACKEND_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "email_draft_agent" / "src"))

from api import tasks
from services.agent_runner import AgentRunError


def test_get_email_returns_original_email(monkeypatch):
    payload = {
        "task_id": "task1",
        "email_id": "email1",
        "email": {"subject": "Hello", "body": "Original body"},
        "basic_information": {"category": "important"},
    }
    monkeypatch.setattr(tasks.task_store, "read_email_for_task", lambda task_id, email_id: payload)

    result = tasks.get_email("task1", "email1")

    assert result == payload


def test_get_email_returns_404_for_missing_email(monkeypatch):
    monkeypatch.setattr(tasks.task_store, "read_email_for_task", lambda task_id, email_id: None)

    with pytest.raises(HTTPException) as exc:
        tasks.get_email("task1", "missing")

    assert exc.value.status_code == 404
    assert exc.value.detail["code"] == "email_not_found"


def test_update_draft_saves_markdown(monkeypatch):
    calls = []

    def fake_update(task_id, email_id, markdown):
        calls.append((task_id, email_id, markdown))
        return {"task_id": task_id, "email_id": email_id, "markdown": markdown}

    monkeypatch.setattr(tasks.task_store, "update_draft_markdown", fake_update)

    result = tasks.update_draft("task1", "email1", tasks.DraftUpdateRequest(markdown="To: a@example.com"))

    assert calls == [("task1", "email1", "To: a@example.com")]
    assert result["markdown"] == "To: a@example.com"


def test_update_draft_returns_404_for_missing_draft(monkeypatch):
    monkeypatch.setattr(tasks.task_store, "update_draft_markdown", lambda task_id, email_id, markdown: None)

    with pytest.raises(HTTPException) as exc:
        tasks.update_draft("task1", "email1", tasks.DraftUpdateRequest(markdown="Draft"))

    assert exc.value.status_code == 404


def test_send_draft_requires_user_approval(monkeypatch):
    monkeypatch.setattr(tasks.task_store, "read_draft_markdown", lambda task_id, email_id: "Draft")

    with pytest.raises(HTTPException) as exc:
        tasks.send_draft("task1", "email1", tasks.SendDraftRequest(approved=False))

    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "send_not_approved"


def test_send_draft_returns_404_for_missing_draft(monkeypatch):
    monkeypatch.setattr(tasks.task_store, "read_draft_markdown", lambda task_id, email_id: None)

    with pytest.raises(HTTPException) as exc:
        tasks.send_draft("task1", "email1", tasks.SendDraftRequest(approved=True))

    assert exc.value.status_code == 404


def test_send_draft_sends_when_approved(monkeypatch):
    calls = []
    monkeypatch.setattr(tasks.task_store, "read_draft_markdown", lambda task_id, email_id: "Draft")

    def fake_send(task_id, email_id):
        calls.append((task_id, email_id))
        return {"task_id": task_id, "email_id": email_id, "sent": True}

    monkeypatch.setattr(tasks, "send_saved_draft", fake_send)

    result = tasks.send_draft("task1", "email1", tasks.SendDraftRequest(approved=True))

    assert calls == [("task1", "email1")]
    assert result["sent"] is True


def test_send_draft_maps_send_errors(monkeypatch):
    monkeypatch.setattr(tasks.task_store, "read_draft_markdown", lambda task_id, email_id: "Draft")
    monkeypatch.setattr(tasks, "send_saved_draft", lambda task_id, email_id: (_ for _ in ()).throw(AgentRunError("bad smtp", code="smtp_send_failed")))

    with pytest.raises(HTTPException) as exc:
        tasks.send_draft("task1", "email1", tasks.SendDraftRequest(approved=True))

    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "smtp_send_failed"


def test_list_emails_for_task_includes_subject(monkeypatch, tmp_path):
    run_dir = tmp_path / "run_task"
    category_dir = run_dir / "important"
    category_dir.mkdir(parents=True)
    email_file = category_dir / "123_task1_subject_slug.json"
    email_file.write_text(
        '{"basic_information":{"subject":"Real Email Title"},"email":{"subject":"Fallback Title"}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(tasks.task_store, "find_classified_run_dir", lambda task_id: run_dir)
    monkeypatch.setattr(tasks.task_store, "relative_path", lambda path: str(path))

    result = tasks.task_store.list_emails_for_task("task1")

    assert result["important"][0]["subject"] == "Real Email Title"
    assert result["important"][0]["email_id"] == "123"
