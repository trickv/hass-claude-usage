"""Verify the integration requests only the user:profile OAuth scope."""

import importlib.util
from pathlib import Path

COMPONENT_DIR = Path(__file__).parent.parent / "custom_components" / "hass_claude_usage"


def _load_const():
    spec = importlib.util.spec_from_file_location("const", COMPONENT_DIR / "const.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_only_user_profile_scope_requested():
    const = _load_const()
    assert const.OAUTH_SCOPES.split() == ["user:profile"]


def test_config_flow_uses_oauth_scopes_constant():
    # config_flow imports homeassistant, so check the source rather than importing it.
    source = (COMPONENT_DIR / "config_flow.py").read_text()
    assert '"scope": OAUTH_SCOPES' in source
    assert "org:create_api_key" not in source
    assert "user:inference" not in source
