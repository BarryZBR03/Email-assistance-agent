import json
import logging
from pathlib import Path
from typing import Any

from email_summary_agent.json_storage import sanitize_filename_part

logger = logging.getLogger(__name__)


def summary_markdown_filename(task_id: str) -> str:
    safe_task_id = sanitize_filename_part(task_id, "task")
    return f"email_summary_{safe_task_id}.md"


DEFAULT_SUMMARY_SYSTEM_PROMPT = (
    "You summarize selected important, work, personal, and other emails. "
    "Use only the provided JSON data. Return Markdown only. "
    "Include concise sections for important emails, work emails, personal emails, other emails, and action items. "
    "Do not invent details that are not present."
)


def create_summary_chain(model, system_prompt: str = ""):
    from langchain_core.output_parsers import StrOutputParser
    from langchain_core.prompts import ChatPromptTemplate

    logger.info("Creating email summary LangChain pipeline")
    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                system_prompt.strip() or DEFAULT_SUMMARY_SYSTEM_PROMPT,
            ),
            (
                "human",
                "Summarize this selected email JSON dump as Markdown.\n"
                "Task ID: {task_id}\n"
                "JSON:\n{dump_json}",
            ),
        ]
    )
    return prompt | model | StrOutputParser()


def load_dump_payload(dump_path: str | Path) -> dict[str, Any]:
    path = Path(dump_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("Selected email dump must contain a JSON object")
    return payload


def summarize_selected_email_dump(
    dump_path: str | Path,
    output_dir: str | Path,
    task_id: str,
    chain,
) -> Path | None:
    path = Path(dump_path)
    payload = load_dump_payload(path)
    email_count = int(payload.get("email_count") or 0)
    logger.info("Loaded selected email dump task_id=%s path=%s email_count=%s", task_id, path, email_count)
    if email_count == 0:
        logger.info("Skipping email summary task_id=%s because selected email dump is empty", task_id)
        return None

    dump_json = json.dumps(payload, ensure_ascii=False, indent=2)
    summary_markdown = chain.invoke({"task_id": task_id, "dump_json": dump_json})
    if not summary_markdown:
        raise RuntimeError("Summary model returned empty content")

    summary_path = Path(output_dir) / summary_markdown_filename(task_id)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(str(summary_markdown).strip() + "\n", encoding="utf-8")
    logger.info("Wrote email summary markdown task_id=%s path=%s", task_id, summary_path)
    return summary_path
