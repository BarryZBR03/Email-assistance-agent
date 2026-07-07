import os
from dataclasses import dataclass
from pathlib import Path

from email_draft_agent.logging_utils import parse_log_level


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
    classified_emails_dir: str
    draft_output_dir: str
    llm_provider: str
    llm_api_key: str | None
    llm_base_url: str
    llm_draft_model: str
    llm_draft_max_concurrency: int
    email_address: str
    smtp_host: str
    smtp_port: int
    smtp_auth_code: str | None
    draft_system_prompt: str
    draft_personality: str
    log_level: str
    draft_log_file: str


def project_root() -> Path:
    return Path(__file__).resolve().parents[3]


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


def parse_positive_int(value: str | None, *, default: int, label: str) -> int:
    raw_value = (value or str(default)).strip()
    try:
        parsed = int(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"{label} must be a positive integer") from exc
    if parsed < 1:
        raise RuntimeError(f"{label} must be a positive integer")
    return parsed


def first_env(env: os._Environ[str] | dict[str, str], *names: str, default: str = "") -> str:
    for name in names:
        value = env.get(name)
        if value is not None and value.strip():
            return value.strip()
    return default


def config_from_env(environ: os._Environ[str] | dict[str, str] | None = None) -> AppConfig:
    env = environ if environ is not None else os.environ
    email_address = env.get("EMAIL_ADDRESS", "").strip() or env.get("IMAP_USER", "").strip()

    return AppConfig(
        classified_emails_dir=env.get("CLASSIFIED_EMAILS_DIR", "classified_emails").strip() or "classified_emails",
        draft_output_dir=env.get("DRAFT_OUTPUT_DIR", "output").strip() or "output",
        llm_provider=parse_llm_provider(env.get("LLM_PROVIDER")),
        llm_api_key=first_env(env, "LLM_API_KEY", "DEEPSEEK_API_KEY") or None,
        llm_base_url=first_env(env, "LLM_BASE_URL", "BASE_URL", "DEEPSEEK_BASE_URL", default="https://api.deepseek.com"),
        llm_draft_model=first_env(env, "LLM_DRAFT_MODEL", "DEEPSEEK_DRAFT_MODEL", default="deepseek-v4-pro"),
        llm_draft_max_concurrency=parse_positive_int(
            env.get("LLM_DRAFT_MAX_CONCURRENCY"),
            default=250,
            label="LLM_DRAFT_MAX_CONCURRENCY",
        ),
        email_address=email_address,
        smtp_host=env.get("SMTP_HOST", "").strip(),
        smtp_port=int(env.get("SMTP_PORT", "465").strip() or "465"),
        smtp_auth_code=env.get("SMTP_AUTH_CODE"),
        draft_system_prompt=env.get("DRAFT_SYSTEM_PROMPT", "").strip(),
        draft_personality=env.get("DRAFT_PERSONALITY", "").strip(),
        log_level=parse_log_level_name(env.get("LOG_LEVEL")),
        draft_log_file=env.get("DRAFT_LOG_FILE", "logs/task_{task_id}/email_draft_agent.log").strip(),
    )
