# Testing

Three tiers, selected by filename suffix and Makefile target.

| Tier | Files | What it does | DB |
| --- | --- | --- | --- |
| **Unit** | `*_unit_test.py` | One function at a time; pure logic or mocked inputs | none |
| **Integration** | `*_integration_test.py` | Several modules working together | test DB |
| **System** | `*_system_test.py` | Real `INSERT/UPDATE/DELETE` against a file copy of a seeded DB | copied DB |

```bash
make unit-test          # ENV=test pytest ./tests/*_unit_test.py
make integration-test   # ENV=test pytest ./tests/*_integration_test.py
make system-test        # ENV=test pytest ./tests/*_system_test.py
make test               # all three
```

All targets set `ENV=test`; `tests/conftest.py` also defaults `CONFIG_FILE` to
`config.example.yaml` so config-dependent code has values without a real `config.yaml`.

## Fixtures (`tests/conftest.py`)

- **`db`** — clean test database (`family_bot_test.db`), tables dropped/recreated around
  the test. Request it in integration tests that touch the database.
- **`system_db`** — builds a small **seeded** database (`family_bot_seed.db`) with a
  pre-existing reminder and calendar event, copies it to `family_bot_system.db`, and
  points the manager at the copy. System tests then perform real SQL CRUD against that
  isolated copy — never the production DB. Cleaned up afterward.

Unit tests request no fixture and never open the database.

## What each tier covers here

- **Unit**: `config` parsing, `embeddings.rank_messages` ranking math, Google event
  normalization + calendar-name lookup (fake service), date helpers.
- **Integration**: reminder data access + date helpers; the calendar pipeline
  (fake Google service → upsert → due-selection → mark reminded).
- **System**: reminder CRUD, calendar CRUD (including the reschedule-resets-reminded
  rule), and message archive + embedding storage — all on the copied seed DB.

## Conventions

- Mirror the source module name: `deps/config.py` → `tests/config_unit_test.py`.
- Keep network/SDK calls out of tests — pass a fake `service` to `google_calendar`
  functions, and never load the sentence-transformers model in unit tests (the ranking
  math takes vectors directly).
- Async tests run under `pytest-asyncio` (`asyncio_mode = auto` in `pyproject.toml`).
