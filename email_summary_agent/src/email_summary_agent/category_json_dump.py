import json
import logging
from pathlib import Path
from typing import Any

from email_summary_agent.json_storage import sanitize_filename_part

logger = logging.getLogger(__name__)

DEFAULT_DUMP_CATEGORIES = ("important", "work", "personal", "other")


def category_dump_filename(task_id: str) -> str:
    safe_task_id = sanitize_filename_part(task_id, "task")
    return f"selected_email_dump_{safe_task_id}.json"


def load_classified_email(path: Path) -> dict[str, Any] | None:
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


def category_from_payload(payload: dict[str, Any]) -> str:
    basic_information = payload.get("basic_information")
    if not isinstance(basic_information, dict):
        return ""
    return str(basic_information.get("category", "")).strip().lower()


def dump_selected_categories(
    run_output_dir: str | Path,
    task_id: str,
    categories: tuple[str, ...] = DEFAULT_DUMP_CATEGORIES,
) -> Path:
    output_dir = Path(run_output_dir)
    selected_categories = {category.strip().lower() for category in categories}
    selected_payloads: list[dict[str, Any]] = []
    scanned = 0

    logger.info(
        "Creating selected category dump task_id=%s run_output_dir=%s categories=%s",
        task_id,
        output_dir,
        ",".join(sorted(selected_categories)),
    )
    for path in sorted(output_dir.glob("*/*.json")):
        scanned += 1
        payload = load_classified_email(path)
        if payload is None:
            continue
        category = category_from_payload(payload)
        if category in selected_categories:
            selected_payloads.append(payload)

    dump_path = output_dir / category_dump_filename(task_id)
    dump_payload = {
        "task_id": task_id,
        "source_run_dir": str(output_dir),
        "categories": sorted(selected_categories),
        "email_count": len(selected_payloads),
        "emails": selected_payloads,
    }
    dump_path.parent.mkdir(parents=True, exist_ok=True)
    dump_path.write_text(json.dumps(dump_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    logger.info(
        "Wrote selected category dump task_id=%s scanned=%s selected=%s path=%s",
        task_id,
        scanned,
        len(selected_payloads),
        dump_path,
    )
    return dump_path
