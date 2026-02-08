# Claude Usage - Home Assistant Integration

A custom Home Assistant integration that monitors your Claude (Anthropic) subscription usage via OAuth.

## Sensors

- **Session Usage** - Current 5-hour session utilization (%)
- **Session Reset Time** - When the session limit resets
- **Week Usage** - Current 7-day utilization, all models (%)
- **Weekly Reset Time** - When the weekly limit resets
- **Weekly Sonnet Usage** - Current 7-day Sonnet utilization (%)
- **Weekly Sonnet Reset Time** - When the Sonnet weekly limit resets
- **Extra Usage Enabled** - Whether extra usage is enabled
- **Extra Usage** - Extra usage utilization (%)
- **Extra Usage Credits** - Credits consumed this month
- **Extra Usage Limit** - Monthly credit limit

## Installation

### HACS (recommended)

1. Add this repository as a custom repository in HACS
2. Restart Home Assistant
3. Install "Claude Usage"
4. Go to Settings → Devices & Services → Add Integration → "Claude Usage"
5. Follow the instructions

### Manual

1. Copy `custom_components/hass_claude_usage/` to your HA `custom_components/` directory
2. Restart Home Assistant
3. Add the integration via the UI

## Setup

The integration uses Anthropic's OAuth flow:

1. When adding the integration, you'll be shown an authorization URL
2. Open the URL in your browser and log in to your Anthropic account
3. After authorizing, you'll be redirected to a page with an authorization code
4. Copy the code and paste it into the Home Assistant config flow

## Options

- **Update interval** - How often to poll the usage API (default: 300 seconds, min: 60, max: 3600).

## Rate Limit

I have found Anthropic rate limits the usage API when you hit it too fast; usually a couple of dozen bursts in a minute is enough. The backoff time is around 24 hours, during which you won't be able to see your usage here, in Claude Code, or on https://claude.ai.  I recommend keeping the polling frequency at 300 :)

## Development

### Pre-commit Hook

Install the pre-commit hook to automatically format code before committing:

```bash
pip install pre-commit
pre-commit install
```

This will run black, isort, ruff, and other checks before each commit.

### Manual Formatting

```bash
pip install black isort ruff
black custom_components/hass_claude_usage/
isort custom_components/hass_claude_usage/
ruff check --fix custom_components/hass_claude_usage/
```

## License

MIT License - see [LICENSE](LICENSE) file for details.
