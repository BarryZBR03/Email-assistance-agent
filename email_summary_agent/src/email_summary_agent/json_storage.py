import json
import logging
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Iterable

from email_summary_agent.email_classification import ClassificationResult
from email_summary_agent.email_fetcher import EmailRecord

logger = logging.getLogger(__name__)


def sanitize_filename_part(value: str, default: str) -> str:
    parts = []
    last_was_separator = False
    for char in value.strip().lower():
        if char.isalnum():
            parts.append(char)
            last_was_separator = False
        elif not last_was_separator:
            parts.append("_")
            last_was_separator = True

    normalized = "".join(parts).strip("_")
    return normalized or default


def parse_email_datetime(value: str) -> datetime | None:
    try:
        parsed = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return None
    if parsed.tzinfo is not None:
        return parsed.replace(tzinfo=None)
    return parsed


def timestamp_from_datetime(value: datetime) -> str:
    return value.strftime("%Y-%m-%d_%H-%M-%S")


def timestamp_from_email_date(value: str, now: datetime | None = None) -> str:
    parsed = parse_email_datetime(value)
    if parsed is None:
        parsed = now or datetime.now()
    return timestamp_from_datetime(parsed)


def email_time_range(emails: Iterable[EmailRecord]) -> tuple[datetime, datetime] | None:
    parsed_dates = [parsed for email in emails if (parsed := parse_email_datetime(email.date))]
    if not parsed_dates:
        return None
    return min(parsed_dates), max(parsed_dates)


def run_output_dir(
    base_output_dir: str | Path,
    emails: Iterable[EmailRecord],
    run_started_at: datetime,
    task_id: str,
) -> Path:
    run_timestamp = timestamp_from_datetime(run_started_at)
    time_range = email_time_range(emails)
    if time_range:
        start, end = time_range
        email_range = f"{timestamp_from_datetime(start)}_to_{timestamp_from_datetime(end)}"
    else:
        email_range = "no_emails"

    safe_task_id = sanitize_filename_part(task_id, "task")
    run_name = f"run_{run_timestamp}__emails_{email_range}__task_{safe_task_id}"
    return Path(base_output_dir) / run_name


def classified_email_filename(
    email_record: EmailRecord,
    task_id: str,
    now: datetime | None = None,
) -> str:
    email_id = sanitize_filename_part(email_record.email_id, "no_email_id")
    safe_task_id = sanitize_filename_part(task_id, "task")
    subject = sanitize_filename_part(email_record.subject, "no_subject")
    return f"{email_id}_{safe_task_id}_{subject}.json"


def classified_email_path(
    email_record: EmailRecord,
    classification: ClassificationResult,
    output_dir: str | Path,
    task_id: str,
    now: datetime | None = None,
) -> Path:
    category = sanitize_filename_part(classification.category, "other")
    return Path(output_dir) / category / classified_email_filename(email_record, task_id, now=now)


def classified_email_payload(
    email_record: EmailRecord,
    classification: ClassificationResult,
) -> dict:
    email_data = email_record.to_dict()
    return {
        "basic_information": {
            "email_id": email_record.email_id,
            "subject": email_record.subject,
            "from": email_record.sender,
            "date": email_record.date,
            "category": classification.category,
            "confidence": classification.confidence,
            "reason": classification.reason,
        },
        "email": email_data,
    }


def write_classified_email(
    email_record: EmailRecord,
    classification: ClassificationResult,
    output_dir: str | Path,
    task_id: str,
    now: datetime | None = None,
) -> Path:
    file_path = classified_email_path(email_record, classification, output_dir, task_id, now=now)
    logger.info(
        "Writing classified email subject=%r category=%s path=%s",
        email_record.subject,
        classification.category,
        file_path,
    )
    file_path.parent.mkdir(parents=True, exist_ok=True)
    payload = classified_email_payload(email_record, classification)
    file_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    logger.info("Wrote classified email file %s", file_path)
    return file_path
