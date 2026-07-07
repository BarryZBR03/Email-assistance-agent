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

Supported model providers include OpenAI-compatible APIs, Anthropic Claude, Codex/OpenAI, and Google Gemini. Provider aliases such as Codex, DeepSeek, Qwen, Kimi, Claude, and Gemini are supported by the app configuration.

## Configuration

The easiest way to configure the app is through the web console after the backend is running. Open the configuration panel in the browser to save mailbox, SMTP, email fetch, classification, model/provider, concurrency, and agent behavior settings. The backend stores those values in a local `.env` file.

If you prefer to pre-fill settings manually, create `.env` from the template:

```bash
cp .env.example .env
```

Then edit `.env` with your mailbox and model API key. Important values include:

```env
EMAIL_ADDRESS=you@example.com
IMAP_HOST=imap.example.com
IMAP_PORT=993
IMAP_USER=you@example.com
IMAP_AUTH_CODE=your-imap-app-password

SMTP_HOST=smtp.example.com
SMTP_PORT=465
SMTP_AUTH_CODE=your-smtp-app-password

LLM_API_KEY=your-llm-api-key
```

Provider and model fields are optional. Leave them unset to use defaults, set them in `.env`, or change them from the web console. `LLM_PROVIDER` accepts aliases such as `codex`, `deepseek`, `qwen`, `kimi`, `claude`, or `gemini`.

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

After the backend is running, open the static frontend directly in a browser:

```text
Fronted/index.html
```

No frontend build step or frontend dev server is required. If your shell is still inside the `backend` directory, the file is at:

```text
../Fronted/index.html
```

The frontend calls API endpoints on the backend at `http://127.0.0.1:8000`. To check that the backend is running, open:

```text
http://127.0.0.1:8000/health
```

Do not use `http://127.0.0.1:8000` as the browser UI. The API root has no route and returns `{"detail":"Not Found"}`. Open `Fronted/index.html` for the web console instead.

From the console you can save and update configuration, test IMAP/SMTP, run summaries, review classified emails, generate drafts, edit drafts, and send approved replies. Use the gear button to reopen configuration at any time.

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
