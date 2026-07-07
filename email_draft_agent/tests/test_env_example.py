from pathlib import Path


DOCUMENTED_ENV_KEYS = {
    "CLASSIFIED_EMAILS_DIR",
    "DRAFT_OUTPUT_DIR",
    "DEEPSEEK_API_KEY",
    "LLM_PROVIDER",
    "LLM_API_KEY",
    "LLM_BASE_URL",
    "LLM_DRAFT_MODEL",
    "BASE_URL",
    "DEEPSEEK_BASE_URL",
    "DEEPSEEK_DRAFT_MODEL",
    "LOG_LEVEL",
    "DRAFT_LOG_FILE",
    "EMAIL_ADDRESS",
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_AUTH_CODE",
    "SUMMARY_SYSTEM_PROMPT",
}


def test_env_example_documents_draft_agent_keys():
    content = Path("../.env.example").read_text(encoding="utf-8")

    for key in DOCUMENTED_ENV_KEYS:
        assert f"{key}=" in content
