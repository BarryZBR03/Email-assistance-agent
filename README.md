# Email Assistance

Email Assistance is a local AI workflow for reviewing email. It can fetch recent messages from IMAP, classify them, generate a Markdown inbox summary, and draft replies for selected messages. A FastAPI backend and static browser console are included for local use.

## Features

- Fetch email from an IMAP inbox.
- Classify messages into configurable categories.
- Save structured per-email JSON for review.
- Generate Markdown inbox summaries.
- Draft replies for selected emails.
- Optionally send approved drafts through SMTP.
- Run from either the web console or the command line.

## Project Structure

```text
.
├── email_summary_agent/   # IMAP fetch, classification, JSON export, summary generation
├── email_draft_agent/     # Classified email lookup, reply drafting, optional SMTP send
├── backend/               # FastAPI orchestration API
├── Fronted/               # Static browser console
├── .env.example           # Public configuration template
└── README.md
```

Runtime directories are created locally when the app runs:

```text
classified_emails/   # generated classified email JSON
output/              # generated summaries and drafts
logs/                # task logs and progress files
.trash/              # locally deleted task artifacts
```

These directories are ignored by Git and should not be committed.

## Requirements

- Python 3.10+
- IMAP access to an email account
- SMTP access if you want to send approved drafts
- An LLM API key for a supported provider

Supported model providers include OpenAI-compatible APIs, Anthropic, and Google Gemini. Provider aliases such as DeepSeek, Qwen, Kimi, Claude, and Gemini are supported by the app configuration.

## Configuration

Create a local `.env` file from the template:

```bash
cp .env.example .env
```

Edit `.env` with your mailbox and model settings. Important values include:

```env
EMAIL_ADDRESS=you@example.com
IMAP_HOST=imap.example.com
IMAP_PORT=993
IMAP_USER=you@example.com
IMAP_AUTH_CODE=your-imap-app-password

SMTP_HOST=smtp.example.com
SMTP_PORT=465
SMTP_AUTH_CODE=your-smtp-app-password

LLM_PROVIDER=openai_compatible
LLM_API_KEY=your-llm-api-key
LLM_BASE_URL=https://api.deepseek.com
LLM_CLASSIFICATION_MODEL=deepseek-v4-flash
LLM_SUMMARY_MODEL=deepseek-v4-pro
LLM_DRAFT_MODEL=deepseek-v4-pro
```

Never commit `.env`, API keys, app passwords, logs, raw email content, or generated outputs.

## Run the Web Console

Install backend dependencies:

```bash
cd backend
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Start the API:

```bash
.venv/bin/python -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Open `Fronted/index.html` in a browser. The frontend expects the API at:

```text
http://127.0.0.1:8000
```

From the console you can save configuration, test IMAP/SMTP, run summaries, review classified emails, generate drafts, edit drafts, and send approved replies.

## Run From the CLI

Install and run the summary agent:

```bash
cd email_summary_agent
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/python get_email_data.py
```

Install and run the draft agent:

```bash
cd email_draft_agent
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/python draft_email.py <task_id> <email_id>
```

Multiple email IDs can be passed as a comma-separated list:

```bash
.venv/bin/python draft_email.py <task_id> <email_id_1>,<email_id_2>
```

## Tests

Run package tests after installing each environment:

```bash
cd email_summary_agent
.venv/bin/python -m pytest -q
```

```bash
cd email_draft_agent
.venv/bin/python -m pytest -q
```

Backend tests:

```bash
cd backend
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m pytest -q
```

Tests mock external systems where practical and should not require real email credentials.

## Security Notes

- Use app passwords or authorization codes for mailbox access.
- Keep `.env` local.
- Review generated drafts before sending.
- Sending email requires an explicit approved send action through the API.
- Generated email JSON, summaries, drafts, and logs may contain private information; keep them out of Git.
