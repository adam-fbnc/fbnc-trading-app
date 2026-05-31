# Development Setup

## Prerequisites

- Python 3.13+
- PostgreSQL 14+ (see options below)

---

## 1. PostgreSQL Setup

Choose either option. Both use the same connection string:
```
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/schwab_trading
```

### Option A — Direct Install (Recommended)

1. Download the installer from [postgresql.org/download/windows](https://www.postgresql.org/download/windows/)
2. Run it with these settings:
   - Username: `postgres`
   - Password: `postgres`
   - Port: `5432`
3. After install, create the database using pgAdmin or the psql shell:
   ```sql
   CREATE DATABASE schwab_trading;
   ```

### Option B — Docker

Requires [Docker Desktop](https://www.docker.com/products/docker-desktop/).

```sh
docker compose up -d
```

This starts postgres:16-alpine on port 5432 and creates the `schwab_trading` database automatically.

---

## 2. Python Environment

```sh
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
```

---

## 3. Environment Variables

Copy `.env.example` to `.env` and fill in your values:

```sh
copy .env.example .env
```

Required variables:

| Variable | Description |
|---|---|
| `SCHWAB_APP_KEY` | From Schwab Developer Portal |
| `SCHWAB_APP_SECRET` | From Schwab Developer Portal |
| `SCHWAB_CALLBACK_URL` | Must match your registered redirect URI |
| `DATABASE_URL` | PostgreSQL connection string |

---

## 4. Run Migrations

```sh
alembic upgrade head
```

---

## 5. Start the API

```sh
uvicorn app.main:app --reload
```

API docs available at: [http://localhost:8000/docs](http://localhost:8000/docs)

---

## First Run — Schwab Authentication

On first startup, `schwabdev` will open a browser window to complete the
Schwab OAuth login (three-legged flow). After granting access, paste the
callback URL back into the terminal. Tokens are stored locally and
refreshed automatically on subsequent runs.
