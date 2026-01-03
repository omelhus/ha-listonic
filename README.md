# Listonic Shopping Lists for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=omelhus&repository=hass-listonic&category=integration)

A Home Assistant custom component that integrates with [Listonic](https://listonic.com) shopping list app.

## Features

- View all your Listonic shopping lists as Home Assistant todo entities
- Add items to lists
- Check/uncheck items
- Delete items
- Create new lists
- Real-time sync with Listonic

## Installation

### HACS (Recommended)

Click the button above or:

1. Open HACS in Home Assistant
2. Click on "Integrations"
3. Click the three dots in the top right corner
4. Select "Custom repositories"
5. Add this repository URL: `https://github.com/omelhus/hass-listonic`
6. Select "Integration" as the category
7. Click "Add"
8. Search for "Listonic" and install it
9. Restart Home Assistant

### Manual Installation

1. Copy the `custom_components/listonic` folder to your Home Assistant's `custom_components` directory
2. Restart Home Assistant

## Configuration

1. Go to Settings > Devices & Services
2. Click "Add Integration"
3. Search for "Listonic"
4. Enter your Listonic email and password
5. Click "Submit"

## Usage

After setup, your Listonic shopping lists will appear as todo entities in Home Assistant. You can:

- View lists in the Todo dashboard
- Add items using the todo.add_item service
- Check off items
- Remove items

### Services

#### todo.add_item
Add an item to a Listonic list.

```yaml
service: todo.add_item
target:
  entity_id: todo.listonic_grocery_list
data:
  item: "Milk"
```

#### todo.update_item
Update an item's status.

```yaml
service: todo.update_item
target:
  entity_id: todo.listonic_grocery_list
data:
  item: "Milk"
  status: completed
```

#### todo.remove_item
Remove an item from a list.

```yaml
service: todo.remove_item
target:
  entity_id: todo.listonic_grocery_list
data:
  item: "Milk"
```

## Troubleshooting

### Authentication Issues
- Ensure you're using the correct email and password for your Listonic account
- The integration uses the same credentials as the Listonic web app

### Sync Issues
- The integration polls for updates every 30 seconds by default
- Changes made in Home Assistant are synced immediately

## Development

```bash
# Clone the repository
git clone https://github.com/omelhus/hass-listonic.git
cd hass-listonic

# Install dependencies with uv
uv sync --all-extras

# Run unit tests
uv run pytest tests/test_api.py

# Run integration tests (requires credentials)
export LISTONIC_EMAIL="your@email.com"
export LISTONIC_PASSWORD="yourpassword"
uv run pytest tests/test_integration.py

# Run all tests with coverage
uv run pytest --cov=custom_components/listonic
```

### GitHub Actions

The repository uses GitHub Actions for CI/CD:

- **Unit Tests**: Run on every push and PR
- **Integration Tests**: Run on PRs against real API (requires secrets)
- **Lint**: Ruff and mypy checks
- **Credential Check**: Hourly check for API credential changes

#### Required Secrets for Integration Tests

Add these secrets to your repository settings:

| Secret | Description |
|--------|-------------|
| `LISTONIC_TEST_EMAIL` | Test account email |
| `LISTONIC_TEST_PASSWORD` | Test account password |

Integration tests automatically clean up any test data created during runs.

## License

MIT License - see LICENSE file for details.

## Disclaimer

This project is not affiliated with, endorsed by, or connected to Listonic in any way. This is an unofficial integration created by reverse-engineering the Listonic web app API for personal use.

Use at your own risk. The API may change at any time without notice.

## Credits

This integration was created by reverse-engineering the Listonic web app API.
