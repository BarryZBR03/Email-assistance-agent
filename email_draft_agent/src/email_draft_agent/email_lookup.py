from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from email_draft_agent.filename_utils import sanitize_filename_part

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ClassifiedEmail:
    path: Path
    payload: dict[str, Any]


def task_run_dirs(classified_emails_dir: str | Path, task_id: str) -> list[Path]:
    base_dir = Path(classified_emails_dir)
    safe_task_id = sanitize_filename_part(task_id, "task")
    run_dirs = [path for path in base_dir.glob(f"run_*__task_{safe_task_id}") if path.is_dir()]
    return sorted(run_dirs, key=lambda path: path.name, reverse=True)


def load_json_object(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.warning("Skipping invalid classified email json path=%s", path)
        return None
    except OSError:
        logger.exception("Failed to read classified email json path=%s", path)
        return None

    if not isinstance(payload, dict):
        logger.warning("Skipping non-object classified email json path=%s", path)
        return None
    return payload


def payload_email_id(payload: dict[str, Any]) -> str:
    basic_information = payload.get("basic_information")
    if isinstance(basic_information, dict):
        email_id = str(basic_information.get("email_id", "")).strip()
        if email_id:
            return email_id

    email = payload.get("email")
    if isinstance(email, dict):
        return str(email.get("email_id", "")).strip()
    return ""


def find_classified_email(classified_emails_dir: str | Path, task_id: str, email_id: str) -> ClassifiedEmail:
    run_dirs = task_run_dirs(classified_emails_dir, task_id)
    if not run_dirs:
        raise RuntimeError(f"No classified email run found for task_id={task_id}")

    run_dir = run_dirs[0]
    logger.info("Searching newest classified email run task_id=%s run_dir=%s", task_id, run_dir)
    for path in sorted(run_dir.glob("*/*.json")):
        payload = load_json_object(path)
        if payload is None:
            continue
        if payload_email_id(payload) == email_id:
            logger.info("Selected classified email task_id=%s email_id=%s path=%s", task_id, email_id, path)
            return ClassifiedEmail(path=path, payload=payload)

    raise RuntimeError(f"No classified email found for task_id={task_id} email_id={email_id} in {run_dir}")
