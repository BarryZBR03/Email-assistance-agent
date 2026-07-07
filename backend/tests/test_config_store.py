import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from services import config_store


def full_payload():
    return config_store.ConfigPayload(
        EMAIL_ADDRESS="user@example.com",
        IMAP_HOST="imap.example.com",
        IMAP_PORT="993",
        IMAP_AUTH_CODE="imap-secret",
        SMTP_HOST="smtp.example.com",
        SMTP_PORT="465",
        SMTP_AUTH_CODE="smtp-secret",
        LLM_API_KEY="llm-secret",
    )


def test_save_config_validates_before_writing(monkeypatch, tmp_path):
    env_path = tmp_path / ".env"
    calls = []
    monkeypatch.setattr(config_store, "ENV_PATH", env_path)
    monkeypatch.setattr(config_store, "_test_imap_env", lambda env: calls.append(("imap", dict(env))))
    monkeypatch.setattr(config_store, "_test_smtp_env", lambda env: calls.append(("smtp", dict(env))))

    result = config_store.save_config(full_payload())

    assert result["configured"] is True
    assert calls[0][0] == "imap"
    assert calls[1][0] == "smtp"
    assert calls[0][1]["IMAP_HOST"] == "imap.example.com"
    assert calls[1][1]["SMTP_HOST"] == "smtp.example.com"
    content = env_path.read_text(encoding="utf-8")
    assert "EMAIL_ADDRESS=user@example.com" in content
    assert "IMAP_USER=user@example.com" in content
    assert "LLM_API_KEY=llm-secret" in content
    assert "DEEPSEEK_API_KEY=llm-secret" in content


def test_save_config_does_not_write_when_validation_fails(monkeypatch, tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("EMAIL_ADDRESS=old@example.com\n", encoding="utf-8")
    monkeypatch.setattr(config_store, "ENV_PATH", env_path)
    monkeypatch.setattr(config_store, "_test_imap_env", lambda env: (_ for _ in ()).throw(RuntimeError("bad imap")))
    monkeypatch.setattr(config_store, "_test_smtp_env", lambda env: None)

    with pytest.raises(RuntimeError, match="bad imap"):
        config_store.save_config(full_payload())

    assert env_path.read_text(encoding="utf-8") == "EMAIL_ADDRESS=old@example.com\n"


def test_save_config_requires_all_fields_before_testing(monkeypatch, tmp_path):
    env_path = tmp_path / ".env"
    calls = []
    monkeypatch.setattr(config_store, "ENV_PATH", env_path)
    monkeypatch.setattr(config_store, "_test_imap_env", lambda env: calls.append("imap"))
    monkeypatch.setattr(config_store, "_test_smtp_env", lambda env: calls.append("smtp"))

    with pytest.raises(RuntimeError, match="Missing required settings"):
        config_store.save_config(config_store.ConfigPayload(EMAIL_ADDRESS="user@example.com"))

    assert calls == []
    assert not env_path.exists()

def test_config_status_returns_values_without_secrets(monkeypatch, tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "EMAIL_ADDRESS=user@example.com\n"
        "IMAP_HOST=imap.example.com\n"
        "IMAP_PORT=993\n"
        "IMAP_AUTH_CODE=imap-secret\n"
        "SMTP_HOST=smtp.example.com\n"
        "SMTP_PORT=465\n"
        "SMTP_AUTH_CODE=smtp-secret\n"
        "LLM_API_KEY=llm-secret\n"
        "DEEPSEEK_API_KEY=deepseek-secret\n"
        "EMAIL_STATUS=all\n"
        "RECENT_DAYS=7\n"
        "EMAIL_CATEGORIES=work,personal,other\n"
        "LLM_PROVIDER=claude\n"
        "LLM_BASE_URL=https://models.example.com/v1\n"
        "LLM_CLASSIFICATION_MODEL=custom-classifier\n"
        "LLM_SUMMARY_MODEL=custom-summary\n"
        "LLM_DRAFT_MODEL=custom-draft\n"
        "DRAFT_PERSONALITY=concise and warm\n"
        "LLM_CLASSIFICATION_MAX_CONCURRENCY=88\n"
        "LLM_DRAFT_MAX_CONCURRENCY=44\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(config_store, "ENV_PATH", env_path)

    status = config_store.config_status()

    assert status["configured"] is True
    assert status["values"]["EMAIL_ADDRESS"] == "user@example.com"
    assert status["values"]["EMAIL_STATUS"] == "all"
    assert status["values"]["LLM_PROVIDER"] == "anthropic"
    assert status["values"]["LLM_BASE_URL"] == "https://models.example.com/v1"
    assert status["values"]["LLM_CLASSIFICATION_MODEL"] == "custom-classifier"
    assert status["values"]["LLM_SUMMARY_MODEL"] == "custom-summary"
    assert status["values"]["LLM_DRAFT_MODEL"] == "custom-draft"
    assert status["values"]["DRAFT_PERSONALITY"] == "concise and warm"
    assert status["values"]["LLM_CLASSIFICATION_MAX_CONCURRENCY"] == "88"
    assert status["values"]["LLM_DRAFT_MAX_CONCURRENCY"] == "44"
    assert status["values"]["LLM_API_KEY"] == ""
    assert status["secrets"] == {"IMAP_AUTH_CODE": True, "SMTP_AUTH_CODE": True, "LLM_API_KEY": True}


def test_save_config_preserves_blank_secret_fields(monkeypatch, tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "EMAIL_ADDRESS=old@example.com\n"
        "IMAP_HOST=imap.example.com\n"
        "IMAP_PORT=993\n"
        "IMAP_AUTH_CODE=imap-secret\n"
        "SMTP_HOST=smtp.example.com\n"
        "SMTP_PORT=465\n"
        "SMTP_AUTH_CODE=smtp-secret\n"
        "LLM_API_KEY=llm-secret\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(config_store, "ENV_PATH", env_path)
    monkeypatch.setattr(config_store, "_test_imap_env", lambda env: None)
    monkeypatch.setattr(config_store, "_test_smtp_env", lambda env: None)

    config_store.save_config(config_store.ConfigPayload(EMAIL_ADDRESS="new@example.com", IMAP_AUTH_CODE="", SMTP_AUTH_CODE="", LLM_API_KEY=""))

    content = env_path.read_text(encoding="utf-8")
    assert "EMAIL_ADDRESS=new@example.com" in content
    assert "IMAP_AUTH_CODE=imap-secret" in content
    assert "SMTP_AUTH_CODE=smtp-secret" in content
    assert "LLM_API_KEY=llm-secret" in content


def test_save_config_replaces_secret_when_new_value_provided(monkeypatch, tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "EMAIL_ADDRESS=user@example.com\n"
        "IMAP_HOST=imap.example.com\n"
        "IMAP_PORT=993\n"
        "IMAP_AUTH_CODE=old-imap\n"
        "SMTP_HOST=smtp.example.com\n"
        "SMTP_PORT=465\n"
        "SMTP_AUTH_CODE=old-smtp\n"
        "LLM_API_KEY=old-llm\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(config_store, "ENV_PATH", env_path)
    monkeypatch.setattr(config_store, "_test_imap_env", lambda env: None)
    monkeypatch.setattr(config_store, "_test_smtp_env", lambda env: None)

    config_store.save_config(config_store.ConfigPayload(IMAP_AUTH_CODE="new-imap", SMTP_AUTH_CODE="new-smtp", LLM_API_KEY="new-llm"))

    content = env_path.read_text(encoding="utf-8")
    assert "IMAP_AUTH_CODE=new-imap" in content
    assert "SMTP_AUTH_CODE=new-smtp" in content
    assert "LLM_API_KEY=new-llm" in content
    assert "DEEPSEEK_API_KEY=new-llm" in content

def test_config_status_falls_back_to_legacy_deepseek_settings(monkeypatch, tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text(
        "DEEPSEEK_BASE_URL=https://legacy.example.com\n"
        "DEEPSEEK_MODEL=legacy-classifier\n"
        "DEEPSEEK_SUMMARY_MODEL=legacy-summary\n"
        "DEEPSEEK_DRAFT_MODEL=legacy-draft\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(config_store, "ENV_PATH", env_path)

    status = config_store.config_status()

    assert status["values"]["LLM_BASE_URL"] == "https://legacy.example.com"
    assert status["values"]["LLM_CLASSIFICATION_MODEL"] == "legacy-classifier"
    assert status["values"]["LLM_SUMMARY_MODEL"] == "legacy-summary"
    assert status["values"]["LLM_DRAFT_MODEL"] == "legacy-draft"


def test_config_status_supports_codex_alias(monkeypatch, tmp_path):
    env_path = tmp_path / ".env"
    env_path.write_text("LLM_PROVIDER=codex\n", encoding="utf-8")
    monkeypatch.setattr(config_store, "ENV_PATH", env_path)

    status = config_store.config_status()

    assert status["values"]["LLM_PROVIDER"] == "openai_compatible"

def test_save_config_writes_base_url_and_legacy_alias(monkeypatch, tmp_path):
    env_path = tmp_path / ".env"
    monkeypatch.setattr(config_store, "ENV_PATH", env_path)
    monkeypatch.setattr(config_store, "_test_imap_env", lambda env: None)
    monkeypatch.setattr(config_store, "_test_smtp_env", lambda env: None)

    payload = full_payload()
    payload.LLM_BASE_URL = "https://models.example.com/v1"
    config_store.save_config(payload)

    content = env_path.read_text(encoding="utf-8")
    assert "LLM_BASE_URL=https://models.example.com/v1" in content
    assert "BASE_URL=https://models.example.com/v1" in content
    assert "DEEPSEEK_BASE_URL=https://models.example.com/v1" in content


def test_save_config_writes_neutral_model_fields_and_legacy_aliases(monkeypatch, tmp_path):
    env_path = tmp_path / ".env"
    monkeypatch.setattr(config_store, "ENV_PATH", env_path)
    monkeypatch.setattr(config_store, "_test_imap_env", lambda env: None)
    monkeypatch.setattr(config_store, "_test_smtp_env", lambda env: None)

    payload = full_payload()
    payload.LLM_PROVIDER = "gemini"
    payload.LLM_CLASSIFICATION_MODEL = "gemini-2.0-flash"
    payload.LLM_SUMMARY_MODEL = "gemini-2.5-pro"
    payload.LLM_DRAFT_MODEL = "gemini-2.5-pro"
    payload.LLM_CLASSIFICATION_MAX_CONCURRENCY = "33"
    payload.LLM_DRAFT_MAX_CONCURRENCY = "22"
    config_store.save_config(payload)

    content = env_path.read_text(encoding="utf-8")
    assert "LLM_PROVIDER=google" in content
    assert "LLM_CLASSIFICATION_MODEL=gemini-2.0-flash" in content
    assert "LLM_SUMMARY_MODEL=gemini-2.5-pro" in content
    assert "LLM_DRAFT_MODEL=gemini-2.5-pro" in content
    assert "LLM_CLASSIFICATION_MAX_CONCURRENCY=33" in content
    assert "LLM_DRAFT_MAX_CONCURRENCY=22" in content
    assert "DEEPSEEK_MODEL=gemini-2.0-flash" in content
    assert "DEEPSEEK_SUMMARY_MODEL=gemini-2.5-pro" in content
    assert "DEEPSEEK_DRAFT_MODEL=gemini-2.5-pro" in content


def test_save_config_rejects_invalid_llm_provider(monkeypatch, tmp_path):
    env_path = tmp_path / ".env"
    monkeypatch.setattr(config_store, "ENV_PATH", env_path)
    monkeypatch.setattr(config_store, "_test_imap_env", lambda env: None)
    monkeypatch.setattr(config_store, "_test_smtp_env", lambda env: None)

    payload = full_payload()
    payload.LLM_PROVIDER = "unsupported"
    with pytest.raises(RuntimeError, match="LLM_PROVIDER"):
        config_store.save_config(payload)


def test_save_config_rejects_invalid_concurrency(monkeypatch, tmp_path):
    env_path = tmp_path / ".env"
    monkeypatch.setattr(config_store, "ENV_PATH", env_path)
    monkeypatch.setattr(config_store, "_test_imap_env", lambda env: None)
    monkeypatch.setattr(config_store, "_test_smtp_env", lambda env: None)

    payload = full_payload()
    payload.LLM_CLASSIFICATION_MAX_CONCURRENCY = "0"
    with pytest.raises(RuntimeError, match="LLM_CLASSIFICATION_MAX_CONCURRENCY"):
        config_store.save_config(payload)

    payload = full_payload()
    payload.LLM_DRAFT_MAX_CONCURRENCY = "bad"
    with pytest.raises(RuntimeError, match="LLM_DRAFT_MAX_CONCURRENCY"):
        config_store.save_config(payload)
