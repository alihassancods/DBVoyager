# Repository Guidelines

## Project Structure & Module Organization

`main.py` is the current application entry point. Place reusable Python code under `src/`:

- `src/db_engine/` contains PostgreSQL connection and query-execution helpers.
- `src/models/` contains Pydantic response models such as `QueryResult` and `DatabaseHealth`.
- `databases/database_healthy/` and `databases/database_defective/` provide seed scripts, SQL schema/index/statistics setup, and incident fixtures for the two demo databases.
- `plan/` holds planning material; it is not runtime code.

Keep database-specific SQL and fixtures in the matching database directory. Add new Python modules within the appropriate `src` package and include an `__init__.py` where needed.

## Build, Test, and Development Commands

This project targets Python 3.14 or newer. Create and activate an environment, then install the runtime dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

`python main.py` runs the current smoke entry point. The dependency list is presently empty even though database modules import `psycopg2`, `python-dotenv`, and `pydantic`; add declared dependencies before relying on a fresh environment. There is no configured build, lint, or automated test command yet.

## Coding Style & Naming Conventions

Follow standard Python style: four-space indentation, `snake_case` for functions, variables, and modules, and `PascalCase` for classes and Pydantic models. Add type annotations to public functions and keep imports grouped: standard library, third-party packages, then local imports. Prefer focused functions such as `get_connection()` and return typed models instead of unstructured dictionaries where a model exists.

## Testing Guidelines

Add tests with `pytest` in a top-level `tests/` directory, mirroring `src/` paths (for example, `tests/db_engine/test_operations.py`). Name files `test_*.py` and test functions `test_*`. Mock database connections for unit tests; reserve healthy/defective database fixtures for explicit integration tests. Once tests are added, run them with `python -m pytest`.

## Commit & Pull Request Guidelines

Recent history uses short, imperative subjects (for example, `Add database` and `Initial checklist commit in dev branch`). Keep commits similarly focused: `Add query timeout handling`. In pull requests, explain the behavior change, list validation performed, link relevant issues or incidents, and include screenshots for UI-facing work. Do not commit credentials: configure database access through environment variables such as `DB_HOST`, `DB_PORT`, `DB_USER`, and `DB_PASSWORD`.
