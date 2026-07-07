from __future__ import annotations

import json
import shutil
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CLASSIFIED_EMAILS_DIR = PROJECT_ROOT / "classified_emails"
LOGS_DIR = PROJECT_ROOT / "logs"
OUTPUT_DIR = PROJECT_ROOT / "output"
TRASH_DIR = PROJECT_ROOT / ".trash" / "tasks"

TASK_ID_RE = re.compile(r"task_([A-Za-z0-9_-]+)")
RUN_TIMESTAMP_RE = re.compile(r"run_(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def relative_path(path: Path | None) -> str | None:
    if path is None:
        return None
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _task_id_from_name(name: str) -> str | None:
    match = TASK_ID_RE.search(name)
    return match.group(1) if match else None


def _parse_run_timestamp(name: str) -> datetime | None:
    match = RUN_TIMESTAMP_RE.search(name)
    if not match:
        return None
    try:
        return datetime.strptime(match.group(1), "%Y-%m-%d_%H-%M-%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _mtime_datetime(path: Path | None) -> datetime | None:
    if path is None or not path.exists():
        return None
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)


def _task_candidate_paths(task_id: str) -> list[Path]:
    paths = []
    run_dir = find_classified_run_dir(task_id)
    if run_dir is not None:
        paths.append(run_dir)
    for path in (log_dir_for_task(task_id), output_dir_for_task(task_id)):
        if path.exists():
            paths.append(path)
    return paths


def _created_at_datetime(task_id: str) -> datetime | None:
    run_dir = find_classified_run_dir(task_id)
    if run_dir is not None:
        parsed = _parse_run_timestamp(run_dir.name)
        if parsed is not None:
            return parsed
    mtimes = [_mtime_datetime(path) for path in _task_candidate_paths(task_id)]
    return max((value for value in mtimes if value is not None), default=None)


def list_task_ids() -> list[str]:
    task_ids: set[str] = set()
    for base in (CLASSIFIED_EMAILS_DIR, LOGS_DIR, OUTPUT_DIR):
        if not base.exists():
            continue
        for path in base.iterdir():
            if not path.is_dir():
                continue
            task_id = _task_id_from_name(path.name)
            if task_id:
                task_ids.add(task_id)
    return sorted(
        task_ids,
        key=lambda task_id: (_created_at_datetime(task_id) or datetime.min.replace(tzinfo=timezone.utc), task_id),
        reverse=True,
    )


def find_classified_run_dir(task_id: str) -> Path | None:
    if not CLASSIFIED_EMAILS_DIR.exists():
        return None
    matches = [
        path
        for path in CLASSIFIED_EMAILS_DIR.glob(f"run_*__task_{task_id}")
        if path.is_dir()
    ]
    if not matches:
        return None
    return sorted(matches, key=lambda path: (path.stat().st_mtime, path.name), reverse=True)[0]



def find_all_classified_run_dirs(task_id: str) -> list[Path]:
    if not CLASSIFIED_EMAILS_DIR.exists():
        return []
    return sorted(path for path in CLASSIFIED_EMAILS_DIR.glob(f"run_*__task_{task_id}") if path.is_dir())


def task_owned_paths(task_id: str) -> list[Path]:
    paths: list[Path] = []
    paths.extend(find_all_classified_run_dirs(task_id))
    for path in (log_dir_for_task(task_id), output_dir_for_task(task_id)):
        if path.exists() and path.is_dir():
            paths.append(path)
    return paths


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
    except ValueError:
        return False
    return True


def _validate_task_path(path: Path) -> None:
    allowed_roots = (CLASSIFIED_EMAILS_DIR, LOGS_DIR, OUTPUT_DIR)
    resolved = path.resolve()
    if not _is_relative_to(resolved, PROJECT_ROOT):
        raise RuntimeError(f"Refusing to move path outside project root: {path}")
    if not any(_is_relative_to(resolved, root) for root in allowed_roots):
        raise RuntimeError(f"Refusing to move non-runtime path: {path}")


def task_is_running(task_id: str) -> bool:
    return any(
        str(read_progress(task_id, draft=draft).get("status")) == "running"
        for draft in (False, True)
        if (draft_progress_path_for_task(task_id) if draft else progress_path_for_task(task_id)).exists()
    )


def move_task_to_trash(task_id: str) -> dict[str, object]:
    if task_is_running(task_id):
        raise RuntimeError("Task is still running and cannot be deleted yet.")

    paths = task_owned_paths(task_id)
    if not paths:
        return {"task_id": task_id, "status": "not_found", "deleted_paths": [], "trash_path": None}

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    task_trash_dir = TRASH_DIR / task_id / timestamp
    moved: list[str] = []
    for path in paths:
        _validate_task_path(path)
        if _is_relative_to(path, CLASSIFIED_EMAILS_DIR):
            destination = task_trash_dir / "classified_emails" / path.name
        elif _is_relative_to(path, LOGS_DIR):
            destination = task_trash_dir / "logs" / path.name
        else:
            destination = task_trash_dir / "output" / path.name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(destination))
        moved.append(relative_path(path) or path.as_posix())

    return {
        "task_id": task_id,
        "status": "deleted",
        "deleted_paths": moved,
        "trash_path": relative_path(task_trash_dir),
    }


def _trash_entry_dir(task_id: str, trash_id: str) -> Path:
    return TRASH_DIR / task_id / trash_id


def _validate_trash_path(path: Path) -> None:
    resolved = path.resolve()
    if not _is_relative_to(resolved, TRASH_DIR):
        raise RuntimeError(f"Refusing to access path outside task trash: {path}")


def _parse_trash_timestamp(trash_id: str) -> datetime | None:
    try:
        return datetime.strptime(trash_id, "%Y%m%d_%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _trashed_email_count(entry_dir: Path) -> int:
    classified_dir = entry_dir / "classified_emails"
    if not classified_dir.exists():
        return 0
    return sum(1 for path in classified_dir.glob("*/*/*.json") if path.is_file())


def _trashed_has_summary(entry_dir: Path, task_id: str) -> bool:
    output_root = entry_dir / "output"
    return any(path.is_file() for path in output_root.glob(f"task_{task_id}/email_summary_{task_id}*.md"))


def _trashed_has_drafts(entry_dir: Path, task_id: str) -> bool:
    output_root = entry_dir / "output"
    return any(path.is_file() for path in output_root.glob(f"task_{task_id}/email_draft_{task_id}_*.md"))


def _trashed_created_at(entry_dir: Path) -> datetime | None:
    classified_root = entry_dir / "classified_emails"
    if classified_root.exists():
        for run_dir in sorted(path for path in classified_root.iterdir() if path.is_dir()):
            parsed = _parse_run_timestamp(run_dir.name)
            if parsed is not None:
                return parsed
    return _mtime_datetime(entry_dir)


def trash_entry_summary(task_id: str, trash_id: str, entry_dir: Path) -> dict[str, object]:
    deleted_at = _parse_trash_timestamp(trash_id) or _mtime_datetime(entry_dir)
    created_at = _trashed_created_at(entry_dir)
    return {
        "task_id": task_id,
        "trash_id": trash_id,
        "deleted_at": deleted_at.isoformat() if deleted_at else None,
        "created_at": created_at.isoformat() if created_at else None,
        "display_title": _display_title(task_id, created_at),
        "email_count": _trashed_email_count(entry_dir),
        "has_summary": _trashed_has_summary(entry_dir, task_id),
        "has_drafts": _trashed_has_drafts(entry_dir, task_id),
        "trash_path": relative_path(entry_dir),
    }


def list_trashed_tasks() -> list[dict[str, object]]:
    if not TRASH_DIR.exists():
        return []
    entries: list[dict[str, object]] = []
    for task_dir in sorted(path for path in TRASH_DIR.iterdir() if path.is_dir()):
        task_id = task_dir.name
        for entry_dir in sorted(path for path in task_dir.iterdir() if path.is_dir()):
            _validate_trash_path(entry_dir)
            entries.append(trash_entry_summary(task_id, entry_dir.name, entry_dir))
    return sorted(entries, key=lambda item: (str(item.get("deleted_at") or ""), str(item.get("task_id") or "")), reverse=True)


def _trash_entry_or_none(task_id: str, trash_id: str) -> Path | None:
    entry_dir = _trash_entry_dir(task_id, trash_id)
    if not entry_dir.exists() or not entry_dir.is_dir():
        return None
    _validate_trash_path(entry_dir)
    return entry_dir


def _restore_sources(entry_dir: Path) -> list[tuple[Path, Path]]:
    pairs: list[tuple[Path, Path]] = []
    roots = (
        (entry_dir / "classified_emails", CLASSIFIED_EMAILS_DIR),
        (entry_dir / "logs", LOGS_DIR),
        (entry_dir / "output", OUTPUT_DIR),
    )
    for source_root, destination_root in roots:
        if not source_root.exists():
            continue
        for source in sorted(path for path in source_root.iterdir() if path.is_dir()):
            _validate_trash_path(source)
            pairs.append((source, destination_root / source.name))
    return pairs


def restore_trashed_task(task_id: str, trash_id: str) -> dict[str, object]:
    entry_dir = _trash_entry_or_none(task_id, trash_id)
    if entry_dir is None:
        return {"task_id": task_id, "trash_id": trash_id, "status": "not_found", "restored_paths": []}

    pairs = _restore_sources(entry_dir)
    conflicts = [relative_path(destination) or destination.as_posix() for _, destination in pairs if destination.exists()]
    if conflicts:
        raise RuntimeError("Cannot restore because active task folders already exist: " + ", ".join(conflicts))

    restored: list[str] = []
    for source, destination in pairs:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(destination))
        restored.append(relative_path(destination) or destination.as_posix())

    _validate_trash_path(entry_dir)
    shutil.rmtree(entry_dir)
    try:
        entry_dir.parent.rmdir()
    except OSError:
        pass
    return {"task_id": task_id, "trash_id": trash_id, "status": "restored", "restored_paths": restored}


def permanently_delete_trashed_task(task_id: str, trash_id: str) -> dict[str, object]:
    entry_dir = _trash_entry_or_none(task_id, trash_id)
    if entry_dir is None:
        return {"task_id": task_id, "trash_id": trash_id, "status": "not_found"}
    _validate_trash_path(entry_dir)
    shutil.rmtree(entry_dir)
    try:
        entry_dir.parent.rmdir()
    except OSError:
        pass
    return {"task_id": task_id, "trash_id": trash_id, "status": "permanently_deleted"}

def output_dir_for_task(task_id: str) -> Path:
    return OUTPUT_DIR / f"task_{task_id}"


def log_dir_for_task(task_id: str) -> Path:
    return LOGS_DIR / f"task_{task_id}"


def progress_path_for_task(task_id: str) -> Path:
    return log_dir_for_task(task_id) / "progress.json"


def draft_progress_path_for_task(task_id: str) -> Path:
    return log_dir_for_task(task_id) / "draft_progress.json"


def summary_path_for_task(task_id: str) -> Path:
    return output_dir_for_task(task_id) / f"email_summary_{task_id}.md"


def list_summary_files(task_id: str) -> list[Path]:
    output_dir = output_dir_for_task(task_id)
    if not output_dir.exists():
        return []
    return sorted(output_dir.glob(f"email_summary_{task_id}*.md"))


def list_draft_files(task_id: str) -> list[Path]:
    output_dir = output_dir_for_task(task_id)
    if not output_dir.exists():
        return []
    return sorted(output_dir.glob(f"email_draft_{task_id}_*.md"))


def list_log_files(task_id: str) -> list[Path]:
    log_dir = log_dir_for_task(task_id)
    if not log_dir.exists():
        return []
    return sorted(path for path in log_dir.iterdir() if path.is_file())


def _email_slug_from_filename(filename: str, task_id: str) -> str:
    stem = Path(filename).stem
    marker = f"_{task_id}_"
    if marker in stem:
        return stem.split(marker, 1)[1]
    parts = stem.split("_", 2)
    return parts[2] if len(parts) == 3 else stem


def _email_id_from_filename(filename: str) -> str:
    return Path(filename).stem.split("_", 1)[0]


def _email_subject_from_file(path: Path, fallback: str) -> str:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback
    if not isinstance(payload, dict):
        return fallback
    basic_information = payload.get("basic_information")
    if isinstance(basic_information, dict):
        subject = str(basic_information.get("subject", "")).strip()
        if subject:
            return subject
    email = payload.get("email")
    if isinstance(email, dict):
        subject = str(email.get("subject", "")).strip()
        if subject:
            return subject
    return fallback


def list_emails_for_task(task_id: str) -> dict[str, list[dict[str, str]]]:
    run_dir = find_classified_run_dir(task_id)
    if run_dir is None:
        return {}

    grouped: dict[str, list[dict[str, str]]] = {}
    for category_dir in sorted(path for path in run_dir.iterdir() if path.is_dir()):
        category = category_dir.name
        grouped[category] = []
        for path in sorted(category_dir.glob("*.json")):
            slug = _email_slug_from_filename(path.name, task_id)
            grouped[category].append(
                {
                    "email_id": _email_id_from_filename(path.name),
                    "task_id": task_id,
                    "category": category,
                    "filename": path.name,
                    "file_path": relative_path(path) or path.as_posix(),
                    "slug": slug,
                    "subject": _email_subject_from_file(path, slug),
                }
            )
    return grouped


def read_email_for_task(task_id: str, email_id: str) -> dict[str, Any] | None:
    run_dir = find_classified_run_dir(task_id)
    if run_dir is None:
        return None

    for path in sorted(run_dir.glob("*/*.json")):
        if _email_id_from_filename(path.name) != email_id:
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        category = path.parent.name
        return {
            "task_id": task_id,
            "email_id": email_id,
            "category": category,
            "filename": path.name,
            "file_path": relative_path(path) or path.as_posix(),
            "slug": _email_slug_from_filename(path.name, task_id),
            "basic_information": payload.get("basic_information") if isinstance(payload.get("basic_information"), dict) else {},
            "email": payload.get("email") if isinstance(payload.get("email"), dict) else {},
        }
    return None


def email_count(task_id: str) -> int:
    return sum(len(items) for items in list_emails_for_task(task_id).values())


def list_drafts(task_id: str, include_content: bool = False) -> list[dict[str, str]]:
    drafts = []
    prefix = f"email_draft_{task_id}_"
    for path in list_draft_files(task_id):
        stem = path.stem
        email_id = stem[len(prefix) :] if stem.startswith(prefix) else stem
        draft = {
            "task_id": task_id,
            "email_id": email_id,
            "filename": path.name,
            "file_path": relative_path(path) or path.as_posix(),
        }
        if include_content:
            draft["markdown"] = path.read_text(encoding="utf-8")
        drafts.append(draft)
    return drafts


def draft_path_for_email(task_id: str, email_id: str) -> Path | None:
    for draft in list_drafts(task_id):
        if draft["email_id"] == email_id:
            return PROJECT_ROOT / draft["file_path"]
    return None


def read_draft_markdown(task_id: str, email_id: str) -> str | None:
    path = draft_path_for_email(task_id, email_id)
    if path is None or not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def update_draft_markdown(task_id: str, email_id: str, markdown: str) -> dict[str, str] | None:
    path = draft_path_for_email(task_id, email_id)
    if path is None or not path.exists():
        return None
    path.write_text(markdown.rstrip() + "\n", encoding="utf-8")
    return {
        "task_id": task_id,
        "email_id": email_id,
        "filename": path.name,
        "file_path": relative_path(path) or path.as_posix(),
        "markdown": path.read_text(encoding="utf-8"),
    }


def _display_title(task_id: str, created_at: datetime | None) -> str:
    if created_at is None:
        return f"Email task {task_id}"
    return f"Email run - {created_at.astimezone().strftime('%Y-%m-%d %H:%M')}"


def default_progress(task_id: str, status: str = "unknown") -> dict[str, Any]:
    return {
        "task_id": task_id,
        "status": status,
        "stage": status,
        "message": "No progress is available for this task.",
        "current": 0,
        "total": 0,
        "updated_at": now_iso(),
    }


def read_progress(task_id: str, draft: bool = False) -> dict[str, Any]:
    path = draft_progress_path_for_task(task_id) if draft else progress_path_for_task(task_id)
    if not path.exists():
        return default_progress(task_id)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default_progress(task_id)
    if not isinstance(payload, dict):
        return default_progress(task_id)
    return {**default_progress(task_id), **payload, "task_id": task_id}


def write_progress(
    task_id: str,
    *,
    status: str,
    stage: str,
    message: str,
    current: int = 0,
    total: int = 0,
    draft: bool = False,
) -> Path:
    path = draft_progress_path_for_task(task_id) if draft else progress_path_for_task(task_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "task_id": task_id,
        "status": status,
        "stage": stage,
        "message": message,
        "current": current,
        "total": total,
        "updated_at": now_iso(),
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def _status_for_task(task_id: str) -> str:
    progress_file = progress_path_for_task(task_id)
    if progress_file.exists():
        return str(read_progress(task_id).get("status", "unknown"))
    if summary_path_for_task(task_id).exists():
        return "completed"
    return "unknown"


def task_summary(task_id: str) -> dict[str, object]:
    classified_run_dir = find_classified_run_dir(task_id)
    output_dir = output_dir_for_task(task_id)
    log_dir = log_dir_for_task(task_id)
    created_at = _created_at_datetime(task_id)
    return {
        "task_id": task_id,
        "created_at": created_at.isoformat() if created_at else None,
        "display_title": _display_title(task_id, created_at),
        "status": _status_for_task(task_id),
        "email_count": email_count(task_id),
        "has_summary": summary_path_for_task(task_id).exists(),
        "has_drafts": bool(list_draft_files(task_id)),
        "has_logs": log_dir.exists() and bool(list_log_files(task_id)),
        "classified_run_path": relative_path(classified_run_dir),
        "log_dir": relative_path(log_dir) if log_dir.exists() else None,
        "output_dir": relative_path(output_dir) if output_dir.exists() else None,
    }


def list_tasks() -> list[dict[str, object]]:
    return [task_summary(task_id) for task_id in list_task_ids()]


def task_metadata(task_id: str) -> dict[str, object] | None:
    if task_id not in set(list_task_ids()):
        return None

    emails = list_emails_for_task(task_id)
    return {
        **task_summary(task_id),
        "available_categories": sorted(emails),
        "email_files": emails,
        "summary_files": [relative_path(path) for path in list_summary_files(task_id)],
        "draft_files": [relative_path(path) for path in list_draft_files(task_id)],
        "log_files": [relative_path(path) for path in list_log_files(task_id)],
    }


def read_summary_markdown(task_id: str) -> str | None:
    path = summary_path_for_task(task_id)
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8")


def latest_task_id() -> str | None:
    task_ids = list_task_ids()
    return task_ids[0] if task_ids else None
