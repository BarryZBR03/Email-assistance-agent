from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

from services.config_store import config_status
from storage import task_store


TASK_ID_RE = re.compile(r"task_([A-Za-z0-9_-]+)")


class AgentRunError(RuntimeError):
    def __init__(self, message: str, code: str = "agent_failed", stdout: str = "", stderr: str = "") -> None:
        super().__init__(message)
        self.code = code
        self.stdout = stdout
        self.stderr = stderr


SECRET_PATTERNS = ("AUTH_CODE", "API_KEY", "TOKEN", "PASSWORD", "SECRET")


def redact(value: str) -> str:
    redacted_lines = []
    for line in value.splitlines():
        if any(pattern in line.upper() for pattern in SECRET_PATTERNS):
            redacted_lines.append("[redacted]")
        else:
            redacted_lines.append(line)
    return "\n".join(redacted_lines)


def _agent_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = os.environ.copy()
    python_paths = [
        str(task_store.PROJECT_ROOT / "email_summary_agent" / "src"),
        str(task_store.PROJECT_ROOT / "email_draft_agent" / "src"),
    ]
    existing = env.get("PYTHONPATH")
    if existing:
        python_paths.append(existing)
    env["PYTHONPATH"] = os.pathsep.join(python_paths)
    if extra:
        env.update(extra)
    return env


def _friendly_failure(stdout: str, stderr: str, fallback: str) -> tuple[str, str]:
    text = f"{stdout}\n{stderr}".lower()
    if "missing imap_host" in text or "missing imap" in text or "configuration is incomplete" in text:
        return "missing_config", "Configuration is incomplete. Complete setup before running agents."
    if "could not log in" in text or "imap login" in text or "unsafe login" in text:
        return "imap_login_failed", "Email login failed. Check the IMAP host, port, email address, and authorization code."
    if "missing deepseek_api_key" in text or "missing llm_api_key" in text or "llm api key" in text:
        return "llm_api_key_missing", "LLM API key is missing. Add it in setup."
    if "no classified email" in text or "draft" in text:
        return "draft_generation_failed", "Draft generation failed. Check the selected email and LLM settings."
    if "0 emails" in text or "no emails" in text:
        return "no_emails_found", "No matching emails were found for the selected filters."
    return "agent_failed", fallback


def _run_command(args: list[str], env_extra: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    try:
        completed = subprocess.run(
            args,
            cwd=task_store.PROJECT_ROOT,
            env=_agent_env(env_extra),
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        raise AgentRunError(f"Failed to start agent command: {exc}") from exc

    if completed.returncode != 0:
        code, message = _friendly_failure(completed.stdout, completed.stderr, "Agent command failed. Check settings and logs.")
        raise AgentRunError(
            message,
            code=code,
            stdout=redact(completed.stdout),
            stderr=redact(completed.stderr),
        )
    return completed


def _task_id_from_output(output: str) -> str | None:
    for line in output.splitlines():
        match = TASK_ID_RE.search(line)
        if match:
            return match.group(1)
    return None


def _ensure_config_ready() -> None:
    status = config_status()
    if not status["configured"]:
        raise AgentRunError(
            "Configuration is incomplete. Complete setup before running agents.",
            code="missing_config",
        )


def prepare_summary_agent() -> dict[str, object]:
    _ensure_config_ready()
    task_id = uuid4().hex[:8]
    task_store.write_progress(
        task_id,
        status="running",
        stage="initializing",
        message="Preparing the summary agent.",
    )
    return {
        "task_id": task_id,
        "status": "running",
        "summary_path": None,
        "classified_run_path": None,
    }


def run_summary_agent_for_task(task_id: str) -> None:
    progress_path = task_store.progress_path_for_task(task_id)
    try:
        completed = _run_command(
            [sys.executable, "email_summary_agent/get_email_data.py"],
            {
                "EMAIL_ASSISTANCE_TASK_ID": task_id,
                "EMAIL_ASSISTANCE_PROGRESS_FILE": str(progress_path),
            },
        )
    except AgentRunError as exc:
        task_store.write_progress(
            task_id,
            status="failed",
            stage="failed",
            message=str(exc),
        )
        return

    detected_task_id = _task_id_from_output(completed.stdout) or task_id
    task_store.write_progress(
        detected_task_id,
        status="completed",
        stage="completed",
        message="Summary is ready.",
        current=1,
        total=1,
    )

def run_draft_agent(task_id: str, email_ids: list[str]) -> list[dict[str, str]]:
    _ensure_config_ready()
    if not email_ids:
        raise AgentRunError("Select at least one email before generating drafts.", code="missing_email_ids")

    generated = []
    total = len(email_ids)
    task_store.write_progress(
        task_id,
        status="running",
        stage="loading_selected_emails",
        message="Loading selected emails.",
        current=0,
        total=0,
        draft=True,
    )
    try:
        draft_progress_path = task_store.draft_progress_path_for_task(task_id)
        task_store.write_progress(
            task_id,
            status="running",
            stage="drafting",
            message=f"Drafting {total} emails.",
            current=0,
            total=total,
            draft=True,
        )
        completed = _run_command(
            [sys.executable, "email_draft_agent/draft_email.py", task_id, ",".join(email_ids)],
            {"EMAIL_ASSISTANCE_DRAFT_PROGRESS_FILE": str(draft_progress_path)},
        )
        draft_paths = []
        for line in completed.stdout.splitlines():
            path = Path(line.strip())
            if not line.strip() or path.suffix != ".md":
                continue
            if not path.is_absolute():
                path = task_store.PROJECT_ROOT / path
            if path.exists():
                draft_paths.append(path)
        for email_id, path in zip(email_ids, draft_paths):
            generated.append(
                {
                    "email_id": email_id,
                    "file_path": task_store.relative_path(path) or path.as_posix(),
                    "markdown": path.read_text(encoding="utf-8"),
                }
            )

        task_store.write_progress(
            task_id,
            status="running",
            stage="saving_drafts",
            message="Saving generated drafts.",
            current=total,
            total=total,
            draft=True,
        )
    except AgentRunError as exc:
        task_store.write_progress(
            task_id,
            status="failed",
            stage="failed",
            message=str(exc),
            current=0,
            total=total,
            draft=True,
        )
        raise

    if not generated:
        selected = set(email_ids)
        generated = [
            draft
            for draft in task_store.list_drafts(task_id, include_content=True)
            if draft["email_id"] in selected
        ]

    task_store.write_progress(
        task_id,
        status="completed",
        stage="completed",
        message="Drafts are ready.",
        current=total,
        total=total,
        draft=True,
    )
    return generated

def send_saved_draft(task_id: str, email_id: str) -> dict[str, object]:
    markdown = task_store.read_draft_markdown(task_id, email_id)
    if markdown is None:
        raise AgentRunError("Draft not found for the selected email.", code="draft_not_found")

    from email_draft_agent.config import config_from_env
    from email_draft_agent.email_sender import send_draft_email

    try:
        sent = send_draft_email(config_from_env(), markdown)
    except RuntimeError as exc:
        raise AgentRunError(str(exc), code="smtp_send_failed") from exc

    return {
        "task_id": task_id,
        "email_id": email_id,
        "sent": True,
        "recipient": sent.recipient,
        "subject": sent.subject,
    }

