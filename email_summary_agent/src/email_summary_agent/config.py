import os
from dataclasses import dataclass

from email_summary_agent.logging_utils import parse_log_level


VALID_EMAIL_STATUSES = {"seen", "unseen", "all"}
DEFAULT_CATEGORIES = ("important", "work", "personal", "promotion", "spam", "other")
VALID_LLM_PROVIDERS = {"openai_compatible", "anthropic", "google"}
LLM_PROVIDER_ALIASES = {
    "": "openai_compatible",
    "openai": "openai_compatible",
    "openai-compatible": "openai_compatible",
    "openai_compatible": "openai_compatible",
    "custom": "openai_compatible",
    "deepseek": "openai_compatible",
    "qwen": "openai_compatible",
    "kimi": "openai_compatible",
    "moonshot": "openai_compatible",
    "anthropic": "anthropic",
    "claude": "anthropic",
    "google": "google",
    "gemini": "google",
}


@dataclass(frozen=True)
class AppConfig:
    imap_host: str
    imap_user: str
    imap_auth_code: str
    imap_port: int
    email_status: str
    recent_days: int
    allowed_senders: frozenset[str]
    categories: tuple[str, ...]
    output_dir: str
    llm_provider: str
    llm_api_key: str | None
    llm_base_url: str
    llm_classification_model: str
    llm_summary_model: str
    llm_classification_max_concurrency: int
    summary_system_prompt: str
    log_level: str
    log_file: str


def parse_email_status(value: str | None) -> str:
    status = (value or "unseen").strip().lower()
    if status not in VALID_EMAIL_STATUSES:
        raise RuntimeError("EMAIL_STATUS must be one of: seen, unseen, all")
    return status


def parse_recent_days(value: str | None) -> int:
    raw_value = (value or "1").strip()
    try:
        days = int(raw_value)
    except ValueError as exc:
        raise RuntimeError("RECENT_DAYS must be a number from 1 to 30") from exc

    if days < 1 or days > 30:
        raise RuntimeError("RECENT_DAYS must be between 1 and 30")
    return days


def parse_positive_int(value: str | None, *, default: int, label: str) -> int:
    raw_value = (value or str(default)).strip()
    try:
        parsed = int(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"{label} must be a positive integer") from exc
    if parsed < 1:
        raise RuntimeError(f"{label} must be a positive integer")
    return parsed


def parse_csv_values(value: str | None) -> tuple[str, ...]:
    return tuple(item.strip() for item in (value or "").split(",") if item.strip())


def parse_allowed_senders(value: str | None) -> frozenset[str]:
    return frozenset(sender.lower() for sender in parse_csv_values(value))


def parse_categories(value: str | None) -> tuple[str, ...]:
    categories = tuple(category.lower() for category in parse_csv_values(value))
    if not categories:
        categories = DEFAULT_CATEGORIES
    if "other" not in categories:
        categories = (*categories, "other")
    return categories


def parse_log_level_name(value: str | None) -> str:
    level_name = (value or "INFO").strip().upper()
    parse_log_level(level_name)
    return level_name


def parse_llm_provider(value: str | None) -> str:
    provider = (value or "openai_compatible").strip().lower()
    normalized = LLM_PROVIDER_ALIASES.get(provider)
    if normalized not in VALID_LLM_PROVIDERS:
        raise RuntimeError("LLM_PROVIDER must be one of: openai_compatible, anthropic, google")
    return normalized


def first_env(env: os._Environ[str] | dict[str, str], *names: str, default: str = "") -> str:
    for name in names:
        value = env.get(name)
        if value is not None and value.strip():
            return value.strip()
    return default


def config_from_env(environ: os._Environ[str] | dict[str, str] | None = None) -> AppConfig:
    env = environ if environ is not None else os.environ

    imap_host = env.get("IMAP_HOST", "").strip()
    imap_user = env.get("IMAP_USER", "").strip()
    imap_auth_code = env.get("IMAP_AUTH_CODE", "").strip()
    if not imap_host or not imap_user or not imap_auth_code:
        raise RuntimeError("Missing IMAP_HOST, IMAP_USER, or IMAP_AUTH_CODE")

    try:
        imap_port = int(env.get("IMAP_PORT", "993").strip())
    except ValueError as exc:
        raise RuntimeError("IMAP_PORT must be a number") from exc

    return AppConfig(
        imap_host=imap_host,
        imap_user=imap_user,
        imap_auth_code=imap_auth_code,
        imap_port=imap_port,
        email_status=parse_email_status(env.get("EMAIL_STATUS")),
        recent_days=parse_recent_days(env.get("RECENT_DAYS")),
        allowed_senders=parse_allowed_senders(env.get("ALLOWED_SENDERS")),
        categories=parse_categories(env.get("EMAIL_CATEGORIES")),
        output_dir=env.get("OUTPUT_DIR", "classified_emails").strip() or "classified_emails",
        llm_provider=parse_llm_provider(env.get("LLM_PROVIDER")),
        llm_api_key=first_env(env, "LLM_API_KEY", "DEEPSEEK_API_KEY") or None,
        llm_base_url=first_env(env, "LLM_BASE_URL", "BASE_URL", "DEEPSEEK_BASE_URL", default="https://api.deepseek.com"),
        llm_classification_model=first_env(env, "LLM_CLASSIFICATION_MODEL", "DEEPSEEK_MODEL", default="deepseek-v4-flash"),
        llm_summary_model=first_env(env, "LLM_SUMMARY_MODEL", "DEEPSEEK_SUMMARY_MODEL", default="deepseek-v4-pro"),
        llm_classification_max_concurrency=parse_positive_int(
            env.get("LLM_CLASSIFICATION_MAX_CONCURRENCY"),
            default=1000,
            label="LLM_CLASSIFICATION_MAX_CONCURRENCY",
        ),
        summary_system_prompt=env.get("SUMMARY_SYSTEM_PROMPT", "").strip(),
        log_level=parse_log_level_name(env.get("LOG_LEVEL")),
        log_file=env.get("LOG_FILE", "logs/task_{task_id}/email_summary_agent.log").strip(),
    )
