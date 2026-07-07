from pathlib import Path


REQUIRED_ENV_KEYS = {
    "IMAP_HOST",
    "IMAP_PORT",
    "IMAP_USER",
    "IMAP_AUTH_CODE",
    "EMAIL_STATUS",
    "RECENT_DAYS",
    "ALLOWED_SENDERS",
    "EMAIL_CATEGORIES",
    "OUTPUT_DIR",
    "DEEPSEEK_API_KEY",
    "LLM_PROVIDER",
    "LLM_API_KEY",
    "LLM_BASE_URL",
    "LLM_CLASSIFICATION_MODEL",
    "LLM_SUMMARY_MODEL",
    "BASE_URL",
    "DEEPSEEK_BASE_URL",
    "DEEPSEEK_MODEL",
    "LANGSMITH_TRACING",
    "LANGSMITH_API_KEY",
    "LOG_LEVEL",
    "LOG_FILE",
}


def test_env_example_documents_required_keys():
    content = Path("../.env.example").read_text(encoding="utf-8")

    for key in REQUIRED_ENV_KEYS:
        assert f"{key}=" in content
