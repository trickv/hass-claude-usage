"""Device naming is user-visible and shared by every platform, so pin it here."""

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

MODULE_PATH = (
    Path(__file__).resolve().parents[1] / "custom_components" / "hass_claude_usage" / "entity.py"
)


def load_entity_module():
    """Load the shared entity helpers without requiring Home Assistant."""
    package = types.ModuleType("hass_claude_usage")
    package.__path__ = [str(MODULE_PATH.parent)]

    device_module = types.ModuleType("homeassistant.helpers.device_registry")
    device_module.DeviceEntryType = SimpleNamespace(SERVICE="service")
    device_module.DeviceInfo = lambda **kwargs: kwargs

    const_module = types.ModuleType("hass_claude_usage.const")
    const_module.CONF_ACCOUNT_NAME = "account_name"
    const_module.CONF_SUBSCRIPTION_LEVEL = "subscription_level"
    const_module.DOMAIN = "hass_claude_usage"

    modules = {
        "hass_claude_usage": package,
        "hass_claude_usage.const": const_module,
        "homeassistant.helpers.device_registry": device_module,
    }
    spec = importlib.util.spec_from_file_location("hass_claude_usage.entity", MODULE_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    with patch.dict(sys.modules, modules):
        spec.loader.exec_module(module)
    return module


def entry(**data):
    return SimpleNamespace(entry_id="abc123", data=data)


class BuildDeviceInfoTest(unittest.TestCase):
    def setUp(self) -> None:
        self.build = load_entity_module().build_device_info

    def test_account_and_plan(self) -> None:
        info = self.build(entry(account_name="Alice", subscription_level="max_20x"))
        self.assertEqual(info["name"], "Claude Usage (Alice - max_20x)")

    def test_account_without_plan(self) -> None:
        info = self.build(entry(account_name="Alice"))
        self.assertEqual(info["name"], "Claude Usage (Alice)")

    def test_no_account(self) -> None:
        info = self.build(entry())
        self.assertEqual(info["name"], "Claude Usage")

    def test_identifiers_are_scoped_to_the_entry(self) -> None:
        info = self.build(entry())
        self.assertEqual(info["identifiers"], {("hass_claude_usage", "abc123")})
        self.assertEqual(info["entry_type"], "service")


if __name__ == "__main__":
    unittest.main()
