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
2. Install "Claude Usage"
3. Restart Home Assistant
4. Go to Settings → Devices & Services → Add Integration → "Claude Usage"

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

- **Update interval** - How often to poll the usage API (default: 300 seconds, min: 60, max: 3600)

## License

MIT License - see [LICENSE](LICENSE) file for details.
