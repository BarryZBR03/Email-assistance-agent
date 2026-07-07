import logging

import pytest

from email_summary_agent.logging_utils import parse_log_level, resolve_log_file, setup_logging


def test_parse_log_level_accepts_known_levels():
    assert parse_log_level("debug") == logging.DEBUG
    assert parse_log_level("INFO") == logging.INFO


def test_parse_log_level_rejects_unknown_level():
    with pytest.raises(RuntimeError, match="LOG_LEVEL"):
        parse_log_level("verbose")


def test_resolve_log_file_replaces_task_id_placeholder():
    assert (
        resolve_log_file("logs/task_{task_id}/email_summary_agent.log", "abc12345")
        == "logs/task_abc12345/email_summary_agent.log"
    )


def test_resolve_log_file_inserts_task_id_before_suffix():
    assert resolve_log_file("logs/email_summary_agent.log", "abc12345") == "logs/email_summary_agent_task_abc12345.log"


def test_resolve_log_file_handles_empty_path():
    assert resolve_log_file("", "abc12345") == ""
    assert resolve_log_file(None, "abc12345") == ""


def test_setup_logging_writes_to_resolved_task_file(tmp_path):
    log_template = tmp_path / "logs" / "task_{task_id}" / "email_summary_agent.log"

    resolved_log_file = setup_logging("INFO", str(log_template), task_id="abc12345")
    logging.getLogger("email_summary_agent.test").info("hello")

    assert resolved_log_file.endswith("task_abc12345/email_summary_agent.log")
    log_file = tmp_path / "logs" / "task_abc12345" / "email_summary_agent.log"
    assert log_file.exists()
    assert "hello" in log_file.read_text(encoding="utf-8")
