# Dietologist

Dietologist is a Telegram nutrition assistant that turns meal descriptions and food photos into editable food entries. It keeps daily targets, reminders and longer-term reports connected through one structured nutrition journal.

## Features

- Meal logging with AI-assisted food analysis and user confirmation.
- Daily, weekly, monthly and yearly reporting backed by a relational data model.
- Private Telegram access, reminders and protected administration endpoints.
- An Android Health Connect companion for synchronizing activity data.

## How it works

API routes and Telegram handlers share a service layer for nutrition, users, activity and reports. SQLAlchemy stores structured records; Alembic contains schema migrations. The Android companion is a separate client.

**Stack:** Python · FastAPI · aiogram · SQLAlchemy · OpenAI · Kotlin

## Getting started

Use Python 3.12 and a separate virtual environment. Run the following commands from this repository's root in Windows PowerShell.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-local.txt
```

The local requirements include the API, Telegram and AI provider clients. The Android Health Connect companion has its own [setup notes](mobile/health-sync-android/README.md).

If you need provider credentials, copy `.env.example` to `.env` and configure only the services you use. Keep `.env` local.

### Start the application

Copy `.env.example` to `.env` and fill only the services you use. Open http://127.0.0.1:8000/docs. The local bootstrap creates a fresh SQLite database and seeds a food catalog. To run your own Telegram bot, set TELEGRAM_BOT_TOKEN and an explicit TELEGRAM_ADMIN_ID or TELEGRAM_ALLOWED_IDS, then run `python -m app.bot.main`.

```powershell
python -m app.local_bootstrap
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

## Example workflow

Create a fictional meal entry, review its nutritional estimate, and open the daily report.

## Testing and limitations

Local API startup, database initialization, food catalog and access boundaries were checked. Live Telegram/AI conversations and Android device synchronization were not independently exercised.

See [Verification](VERIFICATION.md) for the recorded checks and [Limitations](LIMITATIONS.md) for integration requirements.

## Configuration and security

Keep web services bound to `127.0.0.1`. Hosting this application for multiple users requires authentication and separate storage and resource limits. Configure your own provider credentials when a feature requires them; credentials and personal data are not included. See [Security](SECURITY.md) for local configuration and reporting guidance.
