"""Config flow for Claude Usage integration."""

from __future__ import annotations

import logging
import time
from typing import Any
from urllib.parse import urlencode

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback

from .const import (
    CONF_ACCESS_TOKEN,
    CONF_EXPIRES_AT,
    CONF_PKCE_VERIFIER,
    CONF_REFRESH_TOKEN,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    OAUTH_AUTHORIZE_URL,
    OAUTH_CLIENT_ID,
    OAUTH_REDIRECT_URI,
    OAUTH_SCOPES,
    OAUTH_TOKEN_URL,
)
from . import generate_pkce

_LOGGER = logging.getLogger(__name__)


class ClaudeUsageConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Claude Usage."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._pkce_verifier: str | None = None
        self._pkce_challenge: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step - show OAuth URL and collect auth code."""
        errors: dict[str, str] = {}

        if user_input is not None:
            auth_code = user_input.get("auth_code", "").strip()
            if not auth_code:
                errors["auth_code"] = "missing_code"
            else:
                # Exchange code for tokens
                token_data = await self._exchange_code(auth_code)
                if token_data is None:
                    errors["auth_code"] = "exchange_failed"
                else:
                    await self.async_set_unique_id(DOMAIN)
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title="Claude Usage",
                        data={
                            CONF_ACCESS_TOKEN: token_data["access_token"],
                            CONF_REFRESH_TOKEN: token_data.get("refresh_token", ""),
                            CONF_EXPIRES_AT: time.time() + token_data.get("expires_in", 3600),
                        },
                        options={
                            CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL,
                        },
                    )

        # Generate PKCE pair
        self._pkce_verifier, self._pkce_challenge = generate_pkce()

        params = urlencode({
            "response_type": "code",
            "client_id": OAUTH_CLIENT_ID,
            "redirect_uri": OAUTH_REDIRECT_URI,
            "scope": OAUTH_SCOPES,
            "code_challenge": self._pkce_challenge,
            "code_challenge_method": "S256",
        })
        oauth_url = f"{OAUTH_AUTHORIZE_URL}?{params}"

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required("auth_code"): str,
            }),
            description_placeholders={"oauth_url": oauth_url},
            errors=errors,
        )

    async def _exchange_code(self, code: str) -> dict[str, Any] | None:
        """Exchange authorization code for tokens."""
        # The code from the callback URL may contain a fragment; strip it
        if "#" in code:
            code = code.split("#")[0]

        payload = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": OAUTH_CLIENT_ID,
            "redirect_uri": OAUTH_REDIRECT_URI,
            "code_verifier": self._pkce_verifier,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    OAUTH_TOKEN_URL,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as resp:
                    if not resp.ok:
                        body = await resp.text()
                        _LOGGER.error("Token exchange failed (%s): %s", resp.status, body)
                        return None
                    return await resp.json()
        except aiohttp.ClientError:
            _LOGGER.exception("Token exchange request failed")
            return None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Get the options flow."""
        return ClaudeUsageOptionsFlow()


class ClaudeUsageOptionsFlow(OptionsFlow):
    """Handle options for Claude Usage."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current_interval = self.config_entry.options.get(
            CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(CONF_UPDATE_INTERVAL, default=current_interval): vol.All(
                    int, vol.Range(min=60, max=3600)
                ),
            }),
        )
