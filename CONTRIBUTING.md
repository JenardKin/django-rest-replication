# Contributing

Thank you for considering a contribution to `django-rest-replication`.

## Development Setup

```bash
# 1. Clone the repo
git clone https://github.com/JenardKin/django-rest-replication.git
cd django-rest-replication

# 2. Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 3. Create virtual env and install all dependencies
uv sync --group dev

# 4. Run the test suite
uv run pytest

# 5. Run linting and type checks
uv run ruff check src/ tests/
uv run ruff format src/ tests/
uv run mypy src/django_rest_replication/
```

## Project Structure

```
src/django_rest_replication/   # Package source
tests/                    # Test suite
tests/testapp/            # Minimal Django app used by tests
.github/workflows/        # CI configuration
```

## Submitting Changes

1. Fork the repository and create a branch from `main`
2. Make your changes with tests
3. Ensure `pytest`, `ruff check`, and `mypy` all pass
4. Open a pull request — describe what you changed and why

## Reporting Issues

Use [GitHub Issues](https://github.com/JenardKin/django-rest-replication/issues).
Please include your Django version, Python version, and a minimal reproduction.

## Code Style

- Formatting: `ruff format` (enforced in CI)
- Linting: `ruff check` (enforced in CI)
- Types: `mypy --strict` (enforced in CI)
- All public APIs must have docstrings
