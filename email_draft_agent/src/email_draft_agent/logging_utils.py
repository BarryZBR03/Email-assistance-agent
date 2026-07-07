import logging
from pathlib import Path


LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s - %(message)s"


def parse_log_level(value: str | None) -> int:
    level_name = (value or "INFO").strip().upper()
    level = getattr(logging, level_name, None)
    if not isinstance(level, int):
        raise RuntimeError("LOG_LEVEL must be one of: DEBUG, INFO, WARNING, ERROR, CRITICAL")
    return level


def resolve_log_file(log_file: str | None, task_id: str | None = None) -> str:
    if not log_file:
        return ""

    raw_path = log_file.strip()
    if not raw_path:
        return ""
    if task_id and "{task_id}" in raw_path:
        return raw_path.replace("{task_id}", task_id)
    if not task_id:
        return raw_path

    path = Path(raw_path)
    suffix = path.suffix
    stem = path.stem if suffix else path.name
    task_name = f"{stem}_task_{task_id}"
    if suffix:
        return str(path.with_name(f"{task_name}{suffix}"))
    return str(path.with_name(task_name))


def setup_logging(log_level: str = "INFO", log_file: str | None = None, task_id: str | None = None) -> str:
    level = parse_log_level(log_level)
    resolved_log_file = resolve_log_file(log_file, task_id)
    handlers: list[logging.Handler] = [logging.StreamHandler()]

    if resolved_log_file:
        log_path = Path(resolved_log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_path, encoding="utf-8"))

    logging.basicConfig(
        level=level,
        format=LOG_FORMAT,
        handlers=handlers,
        force=True,
    )
    return resolved_log_file
