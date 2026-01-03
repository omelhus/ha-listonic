# Listonic Home Assistant Integration

## Project Overview
Custom Home Assistant component for integrating with Listonic shopping list app (app.listonic.com).

## API Documentation
See `API.md` for the reverse-engineered API documentation.

## Project Structure
```
listonic/
  custom_components/
    listonic/
      __init__.py       # Integration setup
      config_flow.py    # Configuration UI
      const.py          # Constants
      coordinator.py    # Data update coordinator
      manifest.json     # Integration manifest
      api.py            # Listonic API client
      todo.py           # Todo entity for shopping lists
      strings.json      # UI strings
      translations/     # Localization
  tests/
    __init__.py
    conftest.py         # Pytest fixtures
    test_api.py         # API client tests
    test_init.py        # Integration tests
  API.md                # API documentation
  pyproject.toml        # Project configuration
  .env                  # Local credentials (not committed)
```

## Development Commands
```bash
# Install dependencies
uv sync

# Run tests
uv run pytest

# Run tests with coverage
uv run pytest --cov=custom_components/listonic

# Type checking
uv run mypy custom_components/listonic
```

## Testing Credentials
Credentials are stored in `.env` file (not committed to git).
Load with python-dotenv for local testing.

## Home Assistant Integration Type
This integration uses the `todo` platform to expose shopping lists as todo entities.

## Key Implementation Details
- Uses DataUpdateCoordinator for polling updates
- Implements TodoListEntity for each shopping list
- API client handles authentication and token refresh
- Config flow for user-friendly setup

## Constraints
- Never commit credentials
- Use conventional commits
- Keep tests passing
- Follow Home Assistant coding standards
- Always use `uv` to run Python commands - never use `python` or `pip` directly

## Python Environment
Always use `uv` for all Python operations:
```bash
# Run Python scripts
uv run python script.py

# Run pytest
uv run pytest tests/

# Run linting
uv run ruff check .

# Run type checking
uv run mypy custom_components/listonic

# Install dependencies
uv sync --all-extras

# Add a dependency
uv add package-name
```

Never use bare `python`, `pip`, or `pytest` commands - always prefix with `uv run`.
