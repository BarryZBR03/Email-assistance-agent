from pathlib import Path

from email_draft_agent.filename_utils import sanitize_filename_part


def draft_markdown_filename(task_id: str, email_id: str) -> str:
    safe_task_id = sanitize_filename_part(task_id, "task")
    safe_email_id = sanitize_filename_part(email_id, "email")
    return f"email_draft_{safe_task_id}_{safe_email_id}.md"


def write_draft_markdown(
    output_dir: str | Path,
    task_id: str,
    email_id: str,
    source_path: str | Path,
    draft_markdown: str,
) -> Path:
    safe_task_id = sanitize_filename_part(task_id, "task")
    draft_path = Path(output_dir) / f"task_{safe_task_id}" / draft_markdown_filename(task_id, email_id)
    draft_path.parent.mkdir(parents=True, exist_ok=True)
    content = (
        f"Task ID: {task_id}\n"
        f"Email ID: {email_id}\n"
        f"Source: {source_path}\n\n"
        f"{draft_markdown.strip()}\n"
    )
    draft_path.write_text(content, encoding="utf-8")
    return draft_path
