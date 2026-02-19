"""Config flow for Claude Usage integration."""

from __future__ import annotations

import base64
import hashlib
import logging
import secrets
import time
from typing import Any
from urllib.parse import urlencode

import aiohttp
import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import aiohttp_client

from .const import (
    API_BETA_HEADER,
    CONF_ACCESS_TOKEN,
    CONF_ACCOUNT_NAME,
    CONF_EXPIRES_AT,
    CONF_REFRESH_TOKEN,
    CONF_SUBSCRIPTION_LEVEL,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    OAUTH_AUTHORIZE_URL,
    OAUTH_CLIENT_ID,
    OAUTH_REDIRECT_URI,
    OAUTH_SCOPES,
    OAUTH_TOKEN_URL,
    PROFILE_API_URL,
)

_LOGGER = logging.getLogger(__name__)


class ClaudeUsageConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Claude Usage."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._pkce_verifier: str | None = None
        self._pkce_challenge: str | None = None
        self._state: str | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Handle the user OAuth flow - single step."""
        errors: dict[str, str] = {}

        # Generate PKCE and state on first load
        if self._pkce_verifier is None:
            self._pkce_verifier, self._pkce_challenge = generate_pkce()
            self._state = secrets.token_urlsafe(32)

        # Build OAuth URL
        params = urlencode(
            {
                "code": "true",
                "client_id": OAUTH_CLIENT_ID,
                "response_type": "code",
                "redirect_uri": OAUTH_REDIRECT_URI,
                "scope": OAUTH_SCOPES,
                "code_challenge": self._pkce_challenge,
                "code_challenge_method": "S256",
                "state": self._state,
            }
        )
        oauth_url = f"{OAUTH_AUTHORIZE_URL}?{params}"

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
                    # Fetch account info for display
                    account_name, subscription_level = await self._fetch_account_info(
                        token_data["access_token"]
                    )

                    # Build title with name and subscription level
                    title_parts = ["Claude Usage"]
                    if account_name:
                        title_parts.append(f"({account_name}")
                        if subscription_level:
                            title_parts.append(f"- {subscription_level})")
                        else:
                            title_parts[-1] += ")"
                    title = " ".join(title_parts)

                    await self.async_set_unique_id(DOMAIN)
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(
                        title=title,
                        data={
                            CONF_ACCESS_TOKEN: token_data["access_token"],
                            CONF_REFRESH_TOKEN: token_data.get("refresh_token", ""),
                            CONF_EXPIRES_AT: time.time() + token_data.get("expires_in", 3600),
                            CONF_ACCOUNT_NAME: account_name,
                            CONF_SUBSCRIPTION_LEVEL: subscription_level,
                        },
                        options={
                            CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL,
                        },
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required("auth_code"): str,
                }
            ),
            description_placeholders={"url": oauth_url},
            errors=errors,
        )

    async def _exchange_code(self, code: str) -> dict[str, Any] | None:
        """Exchange authorization code for tokens."""
        # The code from the callback URL may contain a # separator with state
        code_parts = code.split("#")
        auth_code = code_parts[0]
        state = code_parts[1] if len(code_parts) > 1 else ""

        # Validate state parameter to prevent CSRF
        if state and self._state and state != self._state:
            _LOGGER.error("OAuth state mismatch - possible CSRF attack")
            return None

        payload = {
            "grant_type": "authorization_code",
            "code": auth_code,
            "state": state,
            "client_id": OAUTH_CLIENT_ID,
            "redirect_uri": OAUTH_REDIRECT_URI,
            "code_verifier": self._pkce_verifier,
        }

        try:
            session = aiohttp_client.async_get_clientsession(self.hass)
            resp = await session.post(
                OAUTH_TOKEN_URL,
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=aiohttp.ClientTimeout(total=15),
            )
            if not resp.ok:
                _LOGGER.error("Token exchange failed (%s)", resp.status)
                return None
            token_data = await resp.json()
            if "access_token" not in token_data:
                _LOGGER.error("Token exchange response missing access_token")
                return None
            return token_data
        except aiohttp.ClientError:
            _LOGGER.exception("Token exchange request failed")
            return None

    async def _fetch_account_info(self, access_token: str) -> tuple[str | None, str | None]:
        """Fetch account name and subscription level from the profile API."""
        try:
            session = aiohttp_client.async_get_clientsession(self.hass)
            resp = await session.get(
                PROFILE_API_URL,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "anthropic-beta": API_BETA_HEADER,
                },
                timeout=aiohttp.ClientTimeout(total=15),
            )
            if not resp.ok:
                _LOGGER.warning("Failed to fetch account profile (%s)", resp.status)
                return None, None
            profile = await resp.json()
            account = profile.get("account", {})

            # Get account name
            account_name = (
                account.get("display_name") or account.get("full_name") or account.get("email")
            )

            # Get subscription level
            subscription_level = None
            if account.get("has_claude_max"):
                subscription_level = "Max"
            elif account.get("has_claude_pro"):
                subscription_level = "Pro"

            return account_name, subscription_level
        except (aiohttp.ClientError, KeyError):
            _LOGGER.exception("Error fetching account info")
            return None, None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Get the options flow."""
        return ClaudeUsageOptionsFlow()


class ClaudeUsageOptionsFlow(OptionsFlow):
    """Handle options for Claude Usage."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        current_interval = self.config_entry.options.get(
            CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_UPDATE_INTERVAL, default=current_interval): vol.All(
                        int, vol.Range(min=60, max=3600)
                    ),
                }
            ),
        )


def generate_pkce() -> tuple[str, str]:
    """Generate PKCE code_verifier and code_challenge."""
    verifier = secrets.token_urlsafe(32)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge
