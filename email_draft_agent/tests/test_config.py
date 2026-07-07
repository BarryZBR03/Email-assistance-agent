import pytest

from email_draft_agent.config import config_from_env

def test_config_from_env_defaults():
    config = config_from_env({})

    assert config.classified_emails_dir == "classified_emails"
    assert config.draft_output_dir == "output"
    assert config.llm_provider == "openai_compatible"
    assert config.llm_base_url == "https://api.deepseek.com"
    assert config.llm_draft_model == "deepseek-v4-pro"
    assert config.llm_draft_max_concurrency == 250
    assert config.email_address == ""
    assert config.smtp_host == ""
    assert config.smtp_port == 465
    assert config.smtp_auth_code is None
    assert config.draft_system_prompt == ""
    assert config.draft_personality == ""
    assert config.log_level == "INFO"
    assert config.draft_log_file == "logs/task_{task_id}/email_draft_agent.log"

def test_config_from_env_parses_values():
    config = config_from_env(
        {
            "CLASSIFIED_EMAILS_DIR": "classified",
            "DRAFT_OUTPUT_DIR": "drafts",
            "LLM_API_KEY": "key",
            "LLM_PROVIDER": "gemini",
            "LLM_BASE_URL": "https://example.com",
            "LLM_DRAFT_MODEL": "custom-model",
            "LLM_DRAFT_MAX_CONCURRENCY": "23",
            "EMAIL_ADDRESS": "user@example.com",
            "SMTP_HOST": "smtp.example.com",
            "SMTP_PORT": "587",
            "SMTP_AUTH_CODE": "smtp-secret",
            "DRAFT_SYSTEM_PROMPT": "Reply as JSON is forbidden.",
            "DRAFT_PERSONALITY": "warm and concise",
            "LOG_LEVEL": "debug",
            "DRAFT_LOG_FILE": "tmp/draft.log",
        }
    )

    assert config.classified_emails_dir == "classified"
    assert config.draft_output_dir == "drafts"
    assert config.llm_api_key == "key"
    assert config.llm_provider == "google"
    assert config.llm_base_url == "https://example.com"
    assert config.llm_draft_model == "custom-model"
    assert config.llm_draft_max_concurrency == 23
    assert config.email_address == "user@example.com"
    assert config.smtp_host == "smtp.example.com"
    assert config.smtp_port == 587
    assert config.smtp_auth_code == "smtp-secret"
    assert config.draft_system_prompt == "Reply as JSON is forbidden."
    assert config.draft_personality == "warm and concise"
    assert config.log_level == "DEBUG"
    assert config.draft_log_file == "tmp/draft.log"

def test_config_rejects_invalid_log_level():
    with pytest.raises(RuntimeError, match="LOG_LEVEL"):
        config_from_env({"LOG_LEVEL": "verbose"})

def test_config_from_env_supports_legacy_deepseek_aliases():
    config = config_from_env({"DEEPSEEK_API_KEY": "key", "BASE_URL": "https://legacy.example.com", "DEEPSEEK_DRAFT_MODEL": "legacy-draft"})

    assert config.llm_api_key == "key"
    assert config.llm_provider == "openai_compatible"
    assert config.llm_base_url == "https://legacy.example.com"
    assert config.llm_draft_model == "legacy-draft"


def test_config_from_env_supports_codex_alias():
    config = config_from_env({"LLM_PROVIDER": "codex"})

    assert config.llm_provider == "openai_compatible"

def test_config_rejects_invalid_llm_provider():
    with pytest.raises(RuntimeError, match="LLM_PROVIDER"):
        config_from_env({"LLM_PROVIDER": "unsupported"})


@pytest.mark.parametrize("value", ["bad", "0", "-1"])
def test_config_rejects_invalid_draft_concurrency(value):
    with pytest.raises(RuntimeError, match="LLM_DRAFT_MAX_CONCURRENCY"):
        config_from_env({"LLM_DRAFT_MAX_CONCURRENCY": value})
