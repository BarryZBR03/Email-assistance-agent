from __future__ import annotations

import imaplib
import os
import smtplib
from pathlib import Path

from dotenv import dotenv_values
from pydantic import BaseModel

from storage.task_store import PROJECT_ROOT


ENV_PATH = PROJECT_ROOT / ".env"

REQUIRED_FIELDS = (
    "EMAIL_ADDRESS",
    "IMAP_HOST",
    "IMAP_PORT",
    "IMAP_AUTH_CODE",
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_AUTH_CODE",
    "LLM_API_KEY",
)

SECRET_FIELDS = {"IMAP_AUTH_CODE", "SMTP_AUTH_CODE", "LLM_API_KEY", "DEEPSEEK_API_KEY"}
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
CONFIG_VALUE_FIELDS = (
    "EMAIL_ADDRESS",
    "IMAP_HOST",
    "IMAP_PORT",
    "EMAIL_STATUS",
    "RECENT_DAYS",
    "ALLOWED_SENDERS",
    "SMTP_HOST",
    "SMTP_PORT",
    "EMAIL_CATEGORIES",
    "LLM_PROVIDER",
    "LLM_BASE_URL",
    "LLM_CLASSIFICATION_MODEL",
    "LLM_SUMMARY_MODEL",
    "LLM_DRAFT_MODEL",
    "LLM_CLASSIFICATION_MAX_CONCURRENCY",
    "LLM_DRAFT_MAX_CONCURRENCY",
    "SUMMARY_SYSTEM_PROMPT",
    "DRAFT_SYSTEM_PROMPT",
    "DRAFT_PERSONALITY",
)


class ConfigPayload(BaseModel):
    EMAIL_ADDRESS: str | None = None
    IMAP_HOST: str | None = None
    IMAP_PORT: str | int | None = None
    IMAP_AUTH_CODE: str | None = None
    SMTP_HOST: str | None = None
    SMTP_PORT: str | int | None = None
    SMTP_AUTH_CODE: str | None = None
    LLM_API_KEY: str | None = None
    LLM_PROVIDER: str | None = None
    LLM_BASE_URL: str | None = None
    LLM_CLASSIFICATION_MODEL: str | None = None
    LLM_SUMMARY_MODEL: str | None = None
    LLM_DRAFT_MODEL: str | None = None
    LLM_CLASSIFICATION_MAX_CONCURRENCY: str | int | None = None
    LLM_DRAFT_MAX_CONCURRENCY: str | int | None = None
    EMAIL_STATUS: str | None = None
    RECENT_DAYS: str | int | None = None
    ALLOWED_SENDERS: str | None = None
    EMAIL_CATEGORIES: str | None = None
    BASE_URL: str | None = None
    DEEPSEEK_BASE_URL: str | None = None
    DEEPSEEK_MODEL: str | None = None
    DEEPSEEK_SUMMARY_MODEL: str | None = None
    DEEPSEEK_DRAFT_MODEL: str | None = None
    SUMMARY_SYSTEM_PROMPT: str | None = None
    DRAFT_SYSTEM_PROMPT: str | None = None
    DRAFT_PERSONALITY: str | None = None

def _read_env() -> dict[str, str]:
    values = dotenv_values(ENV_PATH)
    return {key: value for key, value in values.items() if value is not None}


def _normalize_llm_provider(value: str | None) -> str:
    provider = (value or "openai_compatible").strip().lower()
    normalized = LLM_PROVIDER_ALIASES.get(provider)
    if normalized not in VALID_LLM_PROVIDERS:
        raise RuntimeError("LLM_PROVIDER must be one of: openai_compatible, anthropic, google")
    return normalized


def _first_env(env: dict[str, str], *names: str, default: str = "") -> str:
    for name in names:
        value = env.get(name, "").strip()
        if value:
            return value
    return default


def _configured_value(env: dict[str, str], field: str) -> str:
    if field == "EMAIL_ADDRESS":
        return env.get("EMAIL_ADDRESS", "").strip() or env.get("IMAP_USER", "").strip()
    if field == "LLM_API_KEY":
        return _first_env(env, "LLM_API_KEY", "DEEPSEEK_API_KEY")
    return env.get(field, "").strip()


def _config_values(env: dict[str, str]) -> dict[str, str]:
    values = {field: env.get(field, "").strip() for field in CONFIG_VALUE_FIELDS}
    values["EMAIL_ADDRESS"] = values["EMAIL_ADDRESS"] or env.get("IMAP_USER", "").strip()
    values["LLM_PROVIDER"] = _normalize_llm_provider(values["LLM_PROVIDER"] or env.get("MODEL_PROVIDER", ""))
    values["LLM_BASE_URL"] = values["LLM_BASE_URL"] or _first_env(env, "BASE_URL", "DEEPSEEK_BASE_URL")
    values["LLM_CLASSIFICATION_MODEL"] = values["LLM_CLASSIFICATION_MODEL"] or env.get("DEEPSEEK_MODEL", "").strip()
    values["LLM_SUMMARY_MODEL"] = values["LLM_SUMMARY_MODEL"] or env.get("DEEPSEEK_SUMMARY_MODEL", "").strip()
    values["LLM_DRAFT_MODEL"] = values["LLM_DRAFT_MODEL"] or env.get("DEEPSEEK_DRAFT_MODEL", "").strip()
    values["LLM_CLASSIFICATION_MAX_CONCURRENCY"] = values["LLM_CLASSIFICATION_MAX_CONCURRENCY"] or "1000"
    values["LLM_DRAFT_MAX_CONCURRENCY"] = values["LLM_DRAFT_MAX_CONCURRENCY"] or "250"
    values["LLM_API_KEY"] = ""
    return values


def _secret_status(env: dict[str, str]) -> dict[str, bool]:
    return {
        "IMAP_AUTH_CODE": bool(env.get("IMAP_AUTH_CODE", "").strip()),
        "SMTP_AUTH_CODE": bool(env.get("SMTP_AUTH_CODE", "").strip()),
        "LLM_API_KEY": bool(_configured_value(env, "LLM_API_KEY")),
    }


def config_status() -> dict[str, object]:
    env = _read_env()
    fields = {field: bool(_configured_value(env, field)) for field in REQUIRED_FIELDS}
    missing = [field for field, configured in fields.items() if not configured]
    return {
        "configured": not missing,
        "fields": fields,
        "missing": missing,
        "values": _config_values(env),
        "secrets": _secret_status(env),
    }


def _quote_env_value(value: str) -> str:
    if not value or any(char.isspace() for char in value) or "#" in value or "=" in value:
        return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return value


def save_config(payload: ConfigPayload) -> dict[str, object]:
    current = _read_env()
    updates = {}
    for key, value in payload.model_dump().items():
        if value is None:
            continue
        stripped = str(value).strip()
        if key in SECRET_FIELDS and not stripped:
            continue
        updates[key] = stripped

    if "EMAIL_ADDRESS" in updates:
        updates["IMAP_USER"] = updates["EMAIL_ADDRESS"]
    if "LLM_API_KEY" in updates:
        updates["DEEPSEEK_API_KEY"] = updates["LLM_API_KEY"]
    if "LLM_PROVIDER" in updates:
        updates["LLM_PROVIDER"] = _normalize_llm_provider(updates["LLM_PROVIDER"])
    if "LLM_BASE_URL" in updates:
        updates["BASE_URL"] = updates["LLM_BASE_URL"]
        updates["DEEPSEEK_BASE_URL"] = updates["LLM_BASE_URL"]
    elif "BASE_URL" in updates:
        updates["LLM_BASE_URL"] = updates["BASE_URL"]
        updates["DEEPSEEK_BASE_URL"] = updates["BASE_URL"]
    elif "DEEPSEEK_BASE_URL" in updates:
        updates["LLM_BASE_URL"] = updates["DEEPSEEK_BASE_URL"]
        updates["BASE_URL"] = updates["DEEPSEEK_BASE_URL"]
    if "LLM_CLASSIFICATION_MODEL" in updates:
        updates["DEEPSEEK_MODEL"] = updates["LLM_CLASSIFICATION_MODEL"]
    elif "DEEPSEEK_MODEL" in updates:
        updates["LLM_CLASSIFICATION_MODEL"] = updates["DEEPSEEK_MODEL"]
    if "LLM_SUMMARY_MODEL" in updates:
        updates["DEEPSEEK_SUMMARY_MODEL"] = updates["LLM_SUMMARY_MODEL"]
    elif "DEEPSEEK_SUMMARY_MODEL" in updates:
        updates["LLM_SUMMARY_MODEL"] = updates["DEEPSEEK_SUMMARY_MODEL"]
    if "LLM_DRAFT_MODEL" in updates:
        updates["DEEPSEEK_DRAFT_MODEL"] = updates["LLM_DRAFT_MODEL"]
    elif "DEEPSEEK_DRAFT_MODEL" in updates:
        updates["LLM_DRAFT_MODEL"] = updates["DEEPSEEK_DRAFT_MODEL"]

    merged = {**current, **updates}
    _validate_required_for_save(merged)
    _validate_optional_for_save(merged)
    _test_imap_env(merged)
    _test_smtp_env(merged)

    lines = [f"{key}={_quote_env_value(value)}" for key, value in sorted(merged.items())]
    ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.environ.update(merged)
    return config_status()


def _validate_required_for_save(env: dict[str, str]) -> None:
    missing = [field for field in REQUIRED_FIELDS if not _configured_value(env, field)]
    if missing:
        raise RuntimeError("Missing required settings: " + ", ".join(missing))


def _validate_optional_for_save(env: dict[str, str]) -> None:
    status = env.get("EMAIL_STATUS", "unseen").strip().lower() or "unseen"
    if status not in {"seen", "unseen", "all"}:
        raise RuntimeError("EMAIL_STATUS must be one of: seen, unseen, all")

    try:
        recent_days = int((env.get("RECENT_DAYS", "1") or "1").strip())
    except ValueError as exc:
        raise RuntimeError("RECENT_DAYS must be a number from 1 to 30") from exc
    if recent_days < 1 or recent_days > 30:
        raise RuntimeError("RECENT_DAYS must be between 1 and 30")

    categories = [item.strip() for item in env.get("EMAIL_CATEGORIES", "").split(",") if item.strip()]
    if env.get("EMAIL_CATEGORIES", "").strip() and not categories:
        raise RuntimeError("EMAIL_CATEGORIES must contain at least one category")

    _normalize_llm_provider(env.get("LLM_PROVIDER"))

    for field in ("LLM_CLASSIFICATION_MAX_CONCURRENCY", "LLM_DRAFT_MAX_CONCURRENCY"):
        raw_value = (env.get(field, "") or {"LLM_CLASSIFICATION_MAX_CONCURRENCY": "1000", "LLM_DRAFT_MAX_CONCURRENCY": "250"}[field]).strip()
        try:
            parsed = int(raw_value)
        except ValueError as exc:
            raise RuntimeError(f"{field} must be a positive integer") from exc
        if parsed < 1:
            raise RuntimeError(f"{field} must be a positive integer")


def _merged_test_env(payload: ConfigPayload | None = None) -> dict[str, str]:
    env = _read_env()
    if payload is not None:
        for key, value in payload.model_dump().items():
            if value is None:
                continue
            stripped = str(value).strip()
            if key in SECRET_FIELDS and not stripped:
                continue
            env[key] = stripped
    if env.get("EMAIL_ADDRESS") and not env.get("IMAP_USER"):
        env["IMAP_USER"] = env["EMAIL_ADDRESS"]
    if env.get("LLM_BASE_URL") and not env.get("BASE_URL"):
        env["BASE_URL"] = env["LLM_BASE_URL"]
    if env.get("LLM_API_KEY") and not env.get("DEEPSEEK_API_KEY"):
        env["DEEPSEEK_API_KEY"] = env["LLM_API_KEY"]
    return env


def _port(value: str | None, label: str) -> int:
    try:
        return int((value or "").strip())
    except ValueError as exc:
        raise RuntimeError(f"{label} must be a number") from exc


def _test_imap_env(env: dict[str, str]) -> None:
    host = env.get("IMAP_HOST", "").strip()
    user = env.get("EMAIL_ADDRESS", "").strip() or env.get("IMAP_USER", "").strip()
    auth_code = env.get("IMAP_AUTH_CODE", "").strip()
    port = _port(env.get("IMAP_PORT", "993"), "IMAP_PORT")
    if not host or not user or not auth_code:
        raise RuntimeError("Missing IMAP host, email address, or authorization code")

    try:
        mail = imaplib.IMAP4_SSL(host, port)
        mail.login(user, auth_code)
        mail.select("INBOX")
        mail.logout()
    except imaplib.IMAP4.error as exc:
        raise RuntimeError("IMAP login failed. Check the IMAP settings and authorization code.") from exc
    except OSError as exc:
        raise RuntimeError("Could not connect to the IMAP server. Check the host and port.") from exc


def test_imap(payload: ConfigPayload | None = None) -> dict[str, object]:
    _test_imap_env(_merged_test_env(payload))
    return {"ok": True}


def _test_smtp_env(env: dict[str, str]) -> None:
    host = env.get("SMTP_HOST", "").strip()
    user = env.get("EMAIL_ADDRESS", "").strip() or env.get("IMAP_USER", "").strip()
    auth_code = env.get("SMTP_AUTH_CODE", "").strip()
    port = _port(env.get("SMTP_PORT", "465"), "SMTP_PORT")
    if not host or not user or not auth_code:
        raise RuntimeError("Missing SMTP host, email address, or authorization code")

    try:
        if port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=20)
        else:
            server = smtplib.SMTP(host, port, timeout=20)
            server.starttls()
        server.login(user, auth_code)
        server.quit()
    except smtplib.SMTPAuthenticationError as exc:
        raise RuntimeError("SMTP login failed. Check the SMTP settings and authorization code.") from exc
    except (OSError, smtplib.SMTPException) as exc:
        raise RuntimeError("Could not connect to the SMTP server. Check the host and port.") from exc


def test_smtp(payload: ConfigPayload | None = None) -> dict[str, object]:
    _test_smtp_env(_merged_test_env(payload))
    return {"ok": True}
