# fbnc-trading-app

FastAPI + PostgreSQL + `schwabdev` service that automates a **covered-call
strategy with rule-based rolling** across multiple Schwab accounts.

## Why this exists (the strategy)

The account holds, per underlying: **long shares + short covered call + long
protective put**. The app watches the position's Greeks in real time and signals
when to roll the short call.

Core principle driving the design: **many small rolls beat one big roll.**
Rolling $1 up when the short call hits ~55 delta, into a fresh ~40-delta strike,
repeated ~5 times, is far cheaper than one roll-up-and-out once the strike is
deep ITM. Therefore the system must **not miss a drastic short-call delta move**.

Two refinements already agreed:

- **Escalating ladder.** First roll triggers at 55 delta -> 40 delta. Subsequent
  rolls trigger at progressively higher deltas (58, 61, 64...). Exact numbers are
  deliberately still open.
- **Net-theta override.** After a dip, the short call's positive theta can be
  minimal while the appreciated long put bleeds large negative theta. When *net*
  theta goes negative, roll — even if that means **overriding the cooldown
  period**.

Whipsaw is the enemy of a delta trigger, so triggers read a **smoothed** delta
(EMA / HMA / KAMA), not a raw tick.

## Architecture

Domain-per-package; each package is `router.py` (HTTP) + `service.py` (I/O shell)
+ `models.py` (SQLAlchemy) + `schemas.py` (Pydantic). Pure logic is kept free of
DB and HTTP so it is directly testable.

| Package | Responsibility |
|---|---|
| `app/account` | Accounts, positions, sync from Schwab; `account_alias` support |
| `app/market` | Quotes, option chains, price history, market hours |
| `app/orders` | Order placement and transactions |
| `app/streaming` | Schwab stream: manager, handler, field maps, DB worker thread |
| `app/gex` | Open interest snapshots + gamma exposure / gamma flip |
| `app/pnl` | Position groups and alerts |
| `app/strategy` | **The roll engine.** Greek aggregation, snapshots, smoothing |
| `app/core` | config, database, logging, middleware, schwab client |

### `app/strategy` internals

- `aggregator.py` — **pure**, no DB/HTTP. Aggregates legs into net delta, gamma
  and theta *per underlying*, plus `short_call_*` / `long_put_*` for the rule
  engine. Per-Greek completeness: a missing gamma invalidates only `net_gamma`.
- `service.py` — I/O shell. Stream-first Greek sourcing with a single `quotes()`
  fallback (`source=auto|stream|quote`). Also snapshots and smoothed delta.
- `moving_averages.py` — pure `compute_ema` / `compute_hma` / `compute_kama`.
- `scheduler.py` — APScheduler snapshot job, market-hours gated.
- `streaming.py` — subscribe an account's symbols; read live Greeks from cache.

### Conventions that matter

- Position quantity is **signed**: long > 0, short < 0.
- Option Greek contribution = `signed_qty * greek * 100` (contract multiplier).
  Equity delta = `qty * 1`; equity gamma/theta = 0.
- Short call theta is **collected** (positive contribution); long put theta is
  **paid** (negative). Net theta < 0 means the structure bleeds time value.
- OSI symbols are parsed **right-to-left** (6-char root is space-padded).

## Workflow (follow this)

1. **Create the Jira story first** — board `SCRUM`, strategy epic `SCRUM-32`.
2. Branch off **`master`** (never off another feature branch — that creates an
   accidental stacked PR).
3. Code, then open a PR to `master`.
4. Before merging, verify the PR head SHA matches local — a PR has silently
   merged only its first commit before.

Credentials live in `.env`: `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`,
`GITHUB_TOKEN`, `GITHUB_REPO`, plus `SCHWAB_APP_KEY` / `SCHWAB_APP_SECRET` /
`SCHWAB_CALLBACK_URL` / `DATABASE_URL`.

## Running

```powershell
.\run.ps1 app        # start uvicorn (Ctrl+Shift+B in VS Code does the same)
.\run.ps1 migrate    # alembic upgrade head
.\run.ps1 revision   # alembic revision --autogenerate
.\run.ps1 test
```

The leading `.\` is required — PowerShell does not put the current directory on
`$PATH`. Docs at http://localhost:8000/docs. Full setup: `DEVELOPMENT.md`.

**`--reload` is not always enough** — a stale uvicorn process can keep serving
old code. When behavior does not match the source, fully stop and restart.

## Debugging lessons already paid for

- **Check `alembic current` against `head` first.** A multi-hour 500-error hunt
  turned out to be migrations 0006-0010 never applied. Four "fixes" were shipped
  chasing the wrong cause.
- The real error was **masked** by a ~77,000-parameter SQL dump. The engine now
  sets `hide_parameters=True` and logs `e.orig`. Keep it that way.
- asyncpg's bind-parameter ceiling is **32,767** (not PostgreSQL's 65,535) —
  batch large inserts below it.
- Logging granularity is configurable via `LOG_LEVEL`, `SQL_ECHO`,
  `LOG_REQUEST_BODY`. Detailed logging is a stated product requirement, not
  optional scaffolding.

## Known open item

Schwab **LEVELONE_OPTIONS Greek field numbers are unverified** (assumed
delta=28, gamma=29, theta=30, vega=31, rho=32, underlying=35, mark=37). Raw
`f_*` fields are deliberately retained in `app/streaming/fields.py` so this can
be confirmed empirically via `GET /strategy/stream/quote/{symbol}` during market
hours. A correction is a one-line change.

## Windows / PowerShell notes

- Write temp test scripts to a `.py` file; inline `python -c "..."` quoting
  breaks in PowerShell.
- Avoid unicode arrows in script output — the console is cp1252 and raises
  `UnicodeEncodeError`. Use ASCII (`-->`, `<--`, `ERR`).
