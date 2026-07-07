from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

from email_draft_agent.config import config_from_env, project_root
from email_draft_agent.draft_output import write_draft_markdown
from email_draft_agent.email_draft import create_llm_client, create_draft_chain, draft_email, draft_emails_async
from email_draft_agent.email_lookup import find_classified_email
from email_draft_agent.logging_utils import setup_logging

logger = logging.getLogger(__name__)


def _write_progress(
    task_id: str,
    *,
    status: str,
    stage: str,
    message: str,
    current: int = 0,
    total: int = 0,
) -> None:
    progress_file = os.environ.get("EMAIL_ASSISTANCE_DRAFT_PROGRESS_FILE", "").strip()
    if not progress_file:
        return
    path = Path(progress_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "task_id": task_id,
                "status": status,
                "stage": stage,
                "message": message,
                "current": current,
                "total": total,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )


def parse_csv_arg(value: str, label: str) -> list[str]:
    items = [item.strip() for item in value.split(",") if item.strip()]
    if not items:
        raise RuntimeError(f"{label} must contain at least one value")
    return items


def expand_task_email_pairs(task_ids: list[str], email_ids: list[str]) -> list[tuple[str, str]]:
    if len(task_ids) == 1:
        return [(task_ids[0], email_id) for email_id in email_ids]
    if len(task_ids) == len(email_ids):
        return list(zip(task_ids, email_ids))
    raise RuntimeError("Task id and email id lists must have the same length unless one task id is used with many email ids")


def run(task_id: str, email_id: str) -> str:
    return run_many([task_id], [email_id])[0]


def resolve_project_path(root: Path, value: str) -> str:
    path = Path(value)
    if path.is_absolute():
        return str(path)
    return str(root / path)


def run_many(task_ids: list[str], email_ids: list[str]) -> list[str]:
    pairs = expand_task_email_pairs(task_ids, email_ids)
    first_task_id = pairs[0][0]
    root = project_root()
    load_dotenv(root / ".env")
    config = config_from_env()
    classified_emails_dir = resolve_project_path(root, config.classified_emails_dir)
    draft_output_dir = resolve_project_path(root, config.draft_output_dir)
    draft_log_file = resolve_project_path(root, config.draft_log_file) if config.draft_log_file else ""
    resolved_log_file = setup_logging(config.log_level, draft_log_file, task_id=first_task_id)
    logger.info(
        "Email draft agent run started pairs=%s log_file=%s",
        len(pairs),
        resolved_log_file or "console-only",
    )
    logger.info(
        "Runtime config: classified_emails_dir=%s draft_output_dir=%s llm_provider=%s llm_draft_model=%s log_file=%s",
        classified_emails_dir,
        draft_output_dir,
        config.llm_provider,
        config.llm_draft_model,
        resolved_log_file or "console-only",
    )
    if not config.llm_api_key:
        logger.error("Missing LLM_API_KEY")
        raise RuntimeError("Missing LLM_API_KEY")

    model = create_llm_client(
        config.llm_provider,
        config.llm_api_key,
        config.llm_draft_model,
        config.llm_base_url,
    )
    chain = create_draft_chain(model, config.draft_system_prompt, config.draft_personality)
    classified_emails = []
    for index, (task_id, email_id) in enumerate(pairs, start=1):
        logger.info("Loading classified email %s/%s task_id=%s email_id=%s", index, len(pairs), task_id, email_id)
        classified_emails.append(find_classified_email(classified_emails_dir, task_id, email_id))

    total = len(pairs)
    completed_drafts = 0

    def on_draft_complete(index, payload, draft_markdown):
        nonlocal completed_drafts
        completed_drafts += 1
        task_id, email_id = pairs[index]
        logger.info("Drafted email %s/%s task_id=%s email_id=%s", completed_drafts, total, task_id, email_id)
        _write_progress(
            first_task_id,
            status="running",
            stage="drafting",
            message=f"Drafted {completed_drafts} of {total} emails.",
            current=completed_drafts,
            total=total,
        )

    _write_progress(
        first_task_id,
        status="running",
        stage="drafting",
        message=f"Drafting {total} emails.",
        current=0,
        total=total,
    )
    logger.info(
        "Drafting %s emails concurrently max_concurrency=%s",
        total,
        config.llm_draft_max_concurrency,
    )
    payloads = [classified_email.payload for classified_email in classified_emails]
    if hasattr(chain, "ainvoke") or hasattr(chain, "invoke"):
        draft_markdowns = asyncio.run(
            draft_emails_async(
                payloads,
                chain,
                config.llm_draft_max_concurrency,
                on_complete=on_draft_complete,
            )
        )
    else:
        draft_markdowns = []
        for index, payload in enumerate(payloads):
            draft_markdown = draft_email(payload, chain)
            draft_markdowns.append(draft_markdown)
            on_draft_complete(index, payload, draft_markdown)

    output_paths = []
    _write_progress(
        first_task_id,
        status="running",
        stage="saving_drafts",
        message="Saving generated drafts.",
        current=total,
        total=total,
    )
    for index, ((task_id, email_id), classified_email, draft_markdown) in enumerate(
        zip(pairs, classified_emails, draft_markdowns),
        start=1,
    ):
        output_path = write_draft_markdown(
            draft_output_dir,
            task_id,
            email_id,
            classified_email.path,
            draft_markdown,
        )
        output_paths.append(str(output_path))
        logger.info("Draft %s/%s written task_id=%s email_id=%s output_path=%s", index, len(pairs), task_id, email_id, output_path)

    _write_progress(first_task_id, status="completed", stage="completed", message="Drafts are ready.", current=total, total=total)
    logger.info("Email draft agent run completed output_files=%s", len(output_paths))
    return output_paths


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("task_ids")
    parser.add_argument("email_ids")
    args = parser.parse_args()
    try:
        task_ids = parse_csv_arg(args.task_ids, "task_ids")
        email_ids = parse_csv_arg(args.email_ids, "email_ids")
        for output_path in run_many(task_ids, email_ids):
            print(output_path)
    except Exception:
        logger.exception("Email draft agent run failed")
        raise
