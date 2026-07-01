.PHONY: install run list-calendars test unit-test integration-test system-test lint lint-black lint-pylint lint-mypy format

install:
	uv pip install -e ".[dev]" || pip install -e ".[dev]"

run:
	python3 bot.py

# Debug: print every calendar the service account can see (see docs/google-setup.md).
list-calendars:
	python3 tools/list_calendars.py

# Three test tiers (see docs/testing.md):
#   unit        - pure functions / mocked inputs, no database
#   integration - several modules working together (test DB)
#   system      - real SQL CRUD against a file-based copy of a seeded DB
test: unit-test integration-test system-test

unit-test:
	ENV=test pytest -v -s ./tests/*_unit_test.py

integration-test:
	ENV=test pytest -v -s ./tests/*_integration_test.py

system-test:
	ENV=test pytest -v -s ./tests/*_system_test.py

lint: lint-black lint-pylint lint-mypy

lint-black:
	black --check deps cogs tests bot.py

format:
	black deps cogs tests bot.py

lint-pylint:
	pylint deps cogs || true

lint-mypy:
	mypy deps cogs bot.py
