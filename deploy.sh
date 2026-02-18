#!/bin/bash
# Deploy hass-claude-usage to local Home Assistant config
set -e

SRC="$(dirname "$0")/custom_components/hass_claude_usage"
DEST="/home/trick/docker-services/hass-config/custom_components/hass_claude_usage"

sudo cp "$SRC"/__init__.py "$SRC"/config_flow.py "$SRC"/const.py "$SRC"/icon.png "$SRC"/manifest.json "$SRC"/sensor.py "$SRC"/strings.json "$DEST"/
sudo mkdir -p "$DEST/translations"
sudo cp "$SRC"/translations/en.json "$DEST/translations/"

echo "Deployed to $DEST"
