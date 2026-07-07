import pytest

from email_summary_agent.config import config_from_env, parse_categories


def base_env():
    return {
        "IMAP_HOST": "imap.example.com",
        "IMAP_USER": "user@example.com",
        "IMAP_AUTH_CODE": "secret",
    }

def test_config_from_env_defaults():
    config = config_from_env(base_env())

    assert config.imap_port == 993
    assert config.email_status == "unseen"
    assert config.recent_days == 1
    assert config.allowed_senders == frozenset()
    assert config.output_dir == "classified_emails"
    assert config.llm_provider == "openai_compatible"
    assert config.llm_base_url == "https://api.deepseek.com"
    assert config.llm_classification_model == "deepseek-v4-flash"
    assert config.llm_summary_model == "deepseek-v4-pro"
    assert config.llm_classification_max_concurrency == 1000
    assert config.summary_system_prompt == ""
    assert config.log_level == "INFO"
    assert config.log_file == "logs/task_{task_id}/email_summary_agent.log"

def test_config_from_env_parses_values():
    env = {
        **base_env(),
        "IMAP_PORT": "995",
        "EMAIL_STATUS": "seen",
        "RECENT_DAYS": "7",
        "ALLOWED_SENDERS": " Boss@Example.com , alerts@example.com ",
        "EMAIL_CATEGORIES": "work, finance",
        "OUTPUT_DIR": "out",
        "LLM_API_KEY": "key",
        "LLM_PROVIDER": "claude",
        "LLM_BASE_URL": "https://models.example.com/v1",
        "LLM_CLASSIFICATION_MODEL": "custom-classifier",
        "LLM_SUMMARY_MODEL": "custom-summary",
        "LLM_CLASSIFICATION_MAX_CONCURRENCY": "17",
        "SUMMARY_SYSTEM_PROMPT": "Summarize with bullets.",
        "LOG_LEVEL": "debug",
        "LOG_FILE": "tmp/run.log",
    }

    config = config_from_env(env)

    assert config.imap_port == 995
    assert config.email_status == "seen"
    assert config.recent_days == 7
    assert config.allowed_senders == frozenset({"boss@example.com", "alerts@example.com"})
    assert config.categories == ("work", "finance", "other")
    assert config.output_dir == "out"
    assert config.llm_api_key == "key"
    assert config.llm_provider == "anthropic"
    assert config.llm_base_url == "https://models.example.com/v1"
    assert config.llm_classification_model == "custom-classifier"
    assert config.llm_summary_model == "custom-summary"
    assert config.llm_classification_max_concurrency == 17
    assert config.summary_system_prompt == "Summarize with bullets."
    assert config.log_level == "DEBUG"
    assert config.log_file == "tmp/run.log"

def test_config_requires_imap_credentials():
    with pytest.raises(RuntimeError, match="Missing IMAP_HOST"):
        config_from_env({})


@pytest.mark.parametrize("value", ["bad", "31", "0"])
def test_config_rejects_invalid_recent_days(value):
    with pytest.raises(RuntimeError):
        config_from_env({**base_env(), "RECENT_DAYS": value})

def test_config_rejects_invalid_email_status():
    with pytest.raises(RuntimeError, match="EMAIL_STATUS"):
        config_from_env({**base_env(), "EMAIL_STATUS": "archived"})


def test_parse_categories_defaults_and_adds_other():
    assert "other" in parse_categories("")
    assert parse_categories("work,personal") == ("work", "personal", "other")

def test_config_rejects_invalid_log_level():
    with pytest.raises(RuntimeError, match="LOG_LEVEL"):
        config_from_env({**base_env(), "LOG_LEVEL": "verbose"})

def test_config_from_env_supports_legacy_deepseek_aliases():
    config = config_from_env({**base_env(), "DEEPSEEK_API_KEY": "key", "BASE_URL": "https://legacy.example.com", "DEEPSEEK_MODEL": "legacy-classifier", "DEEPSEEK_SUMMARY_MODEL": "legacy-summary"})

    assert config.llm_api_key == "key"
    assert config.llm_provider == "openai_compatible"
    assert config.llm_base_url == "https://legacy.example.com"
    assert config.llm_classification_model == "legacy-classifier"
    assert config.llm_summary_model == "legacy-summary"


def test_config_from_env_supports_codex_alias():
    config = config_from_env({**base_env(), "LLM_PROVIDER": "codex"})

    assert config.llm_provider == "openai_compatible"

def test_config_rejects_invalid_llm_provider():
    with pytest.raises(RuntimeError, match="LLM_PROVIDER"):
        config_from_env({**base_env(), "LLM_PROVIDER": "unsupported"})


@pytest.mark.parametrize("value", ["bad", "0", "-1"])
def test_config_rejects_invalid_classification_concurrency(value):
    with pytest.raises(RuntimeError, match="LLM_CLASSIFICATION_MAX_CONCURRENCY"):
        config_from_env({**base_env(), "LLM_CLASSIFICATION_MAX_CONCURRENCY": value})
