from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv

from email_summary_agent.category_json_dump import dump_selected_categories
from email_summary_agent.config import config_from_env
from email_summary_agent.email_classification import (
    classify_email,
    classify_emails_async,
    create_classification_chain,
    create_llm_client,
)
from email_summary_agent.email_fetcher import fetch_emails
from email_summary_agent.email_summary import create_summary_chain, summarize_selected_email_dump
from email_summary_agent.json_storage import run_output_dir, write_classified_email
from email_summary_agent.logging_utils import setup_logging

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
    progress_file = os.environ.get("EMAIL_ASSISTANCE_PROGRESS_FILE", "").strip()
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


def run() -> list[str]:
    run_started_at = datetime.now()
    task_id = os.environ.get("EMAIL_ASSISTANCE_TASK_ID", "").strip() or uuid4().hex[:8]
    _write_progress(task_id, status="running", stage="initializing", message="Preparing configuration.")
    try:
        load_dotenv()
        config = config_from_env()
        resolved_log_file = setup_logging(config.log_level, config.log_file, task_id=task_id)
        logger.info("Email summary agent run started task_id=%s log_file=%s", task_id, resolved_log_file or "console-only")
        logger.info("Dotenv loaded and config parsed")
        logger.info(
            "Runtime config: imap_host=%s imap_port=%s email_status=%s recent_days=%s "
            "allowed_senders=%s categories=%s output_dir=%s llm_provider=%s "
            "llm_classification_model=%s llm_summary_model=%s log_file=%s",
            config.imap_host,
            config.imap_port,
            config.email_status,
            config.recent_days,
            len(config.allowed_senders),
            ",".join(config.categories),
            config.output_dir,
            config.llm_provider,
            config.llm_classification_model,
            config.llm_summary_model,
            resolved_log_file or "console-only",
        )
        if not config.llm_api_key:
            logger.error("Missing LLM_API_KEY")
            raise RuntimeError("Missing LLM_API_KEY")

        _write_progress(task_id, status="running", stage="initializing", message="Creating classification model.")
        logger.info("Creating classification LangChain model")
        model = create_llm_client(
            config.llm_provider,
            config.llm_api_key,
            config.llm_classification_model,
            config.llm_base_url,
        )
        chain = create_classification_chain(model)
        logger.info("Classification chain created")

        output_paths = []
        _write_progress(task_id, status="running", stage="connecting_email", message="Connecting to the mailbox.")
        _write_progress(task_id, status="running", stage="fetching_emails", message="Fetching recent emails.")
        emails = fetch_emails(config)
        _write_progress(
            task_id,
            status="running",
            stage="cleaning_emails",
            message=f"Preparing {len(emails)} emails for classification.",
            current=0,
            total=len(emails),
        )
        output_dir = run_output_dir(config.output_dir, emails, run_started_at, task_id)
        logger.info(
            "Fetched %s emails for classification task_id=%s run_output_dir=%s",
            len(emails),
            task_id,
            output_dir,
        )
        total_emails = len(emails)
        completed_classifications = 0

        def on_classification_complete(index, email_record, classification):
            nonlocal completed_classifications
            completed_classifications += 1
            logger.info(
                "Classified email %s/%s task_id=%s: subject=%r sender=%r category=%s",
                index + 1,
                total_emails,
                task_id,
                email_record.subject,
                email_record.sender,
                classification.category,
            )
            _write_progress(
                task_id,
                status="running",
                stage="classifying_emails",
                message=f"Classified {completed_classifications} of {total_emails} emails.",
                current=completed_classifications,
                total=total_emails,
            )

        _write_progress(
            task_id,
            status="running",
            stage="classifying_emails",
            message=f"Classifying {total_emails} emails.",
            current=0,
            total=total_emails,
        )
        logger.info(
            "Classifying %s emails concurrently task_id=%s max_concurrency=%s",
            total_emails,
            task_id,
            config.llm_classification_max_concurrency,
        )
        classifications = asyncio.run(
            classify_emails_async(
                email_records=emails,
                categories=config.categories,
                chain=chain,
                max_concurrency=config.llm_classification_max_concurrency,
                on_complete=on_classification_complete,
            )
        )
        for index, (email_record, classification) in enumerate(zip(emails, classifications), start=1):
            output_path = write_classified_email(email_record, classification, output_dir, task_id)
            output_paths.append(str(output_path))
            logger.info("Email %s/%s written to %s", index, len(emails), output_path)

        _write_progress(task_id, status="running", stage="saving_outputs", message="Saving classified email outputs.")
        dump_path = dump_selected_categories(output_dir, task_id)
        output_paths.append(str(dump_path))

        _write_progress(task_id, status="running", stage="generating_summary", message="Generating summary markdown.")
        logger.info("Creating summary LangChain model task_id=%s", task_id)
        summary_model = create_llm_client(
            config.llm_provider,
            config.llm_api_key,
            config.llm_summary_model,
            config.llm_base_url,
        )
        summary_chain = create_summary_chain(summary_model, config.summary_system_prompt)
        summary_output_dir = Path("output") / f"task_{task_id}"
        summary_path = summarize_selected_email_dump(dump_path, summary_output_dir, task_id, summary_chain)
        if summary_path is not None:
            output_paths.append(str(summary_path))

        _write_progress(task_id, status="completed", stage="completed", message="Summary is ready.", current=1, total=1)
        logger.info(
            "Email summary agent run completed task_id=%s output_files=%s run_output_dir=%s",
            task_id,
            len(output_paths),
            output_dir,
        )
        return output_paths
    except Exception as exc:
        _write_progress(task_id, status="failed", stage="failed", message=str(exc))
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.parse_args()
    try:
        for output_path in run():
            print(output_path)
    except Exception:
        logger.exception("Email summary agent run failed")
        raise
