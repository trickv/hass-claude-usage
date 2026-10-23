"""Test token-refresh error classification, retries and response cleanup."""

import asyncio
import traceback
import unittest
from datetime import UTC, datetime
from email.utils import format_datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components import hass_claude_usage as integration


class Request:
    """Support both aiohttp request awaiting and its async context manager."""

    def __init__(self, status=200, data=None, headers=None):
        self.response = SimpleNamespace(
            status=status,
            ok=status < 400,
            headers=headers or {},
            json=AsyncMock(return_value=data),
        )
        self.released = False

    def __await__(self):
        async def response():
            return self.response

        return response().__await__()

    async def __aenter__(self):
        return self.response

    async def __aexit__(self, *_args):
        self.released = True


class TokenRefreshTests(unittest.IsolatedAsyncioTestCase):
    """Exercise the actual coordinator with a mocked HTTP session."""

    async def asyncSetUp(self):
        self.clock = SimpleNamespace(time=Mock(return_value=1000), monotonic=Mock(return_value=100))
        clock_patch = patch.object(integration, "time", self.clock)
        clock_patch.start()
        self.addCleanup(clock_patch.stop)

    def coordinator(self, request):
        """Create a coordinator using synthetic credentials and no network."""
        entry = SimpleNamespace(
            data={"expires_at": 0, "refresh_token": "test-refresh"},
            options={},
            async_on_unload=Mock(),
        )
        hass = Mock(spec=HomeAssistant)
        hass.config_entries = SimpleNamespace(async_update_entry=Mock())
        coordinator = integration.ClaudeUsageCoordinator(hass, entry)
        self.post = Mock(return_value=request)
        session_patch = patch.object(
            integration.aiohttp_client,
            "async_get_clientsession",
            return_value=SimpleNamespace(post=self.post),
        )
        session_patch.start()
        self.addCleanup(session_patch.stop)
        return coordinator

    async def test_transient_failures_do_not_request_reauthentication(self):
        """Rate limits, server errors and non-auth 400s retain the credentials."""
        for status in (400, 429, 500, 503):
            with self.subTest(status=status):
                request = Request(status, {"error": "invalid_request"}, {"Retry-After": "120"})
                coordinator = self.coordinator(request)
                with self.assertRaises(UpdateFailed):
                    await coordinator._ensure_valid_token()
                self.assertTrue(request.released)
                self.clock.monotonic.return_value = 101
                with self.assertRaises(UpdateFailed):
                    await coordinator._ensure_valid_token()
                self.post.assert_called_once()
                coordinator.hass.config_entries.async_update_entry.assert_not_called()
                self.clock.monotonic.return_value = 100

    async def test_rejected_refresh_token_still_requests_reauthentication(self):
        """A rejected grant or explicit auth status must still trigger reauth."""
        for status in (400, 401, 403):
            with self.subTest(status=status):
                request = Request(status, {"error": "invalid_grant"})
                coordinator = self.coordinator(request)
                with self.assertRaises(ConfigEntryAuthFailed):
                    await coordinator._ensure_valid_token()
                self.assertTrue(request.released)

    async def test_missing_refresh_token_requests_reauthentication(self):
        """Missing local credentials must not cause a network request."""
        coordinator = self.coordinator(Request())
        coordinator.config_entry.data.clear()
        with self.assertRaises(ConfigEntryAuthFailed):
            await coordinator._ensure_valid_token()
        self.post.assert_not_called()

    async def test_success_persists_rotated_tokens_and_clears_deferral(self):
        """A later successful attempt persists the new tokens and expiration."""
        request = Request(
            200, {"access_token": "test-access", "refresh_token": "test-new", "expires_in": 3600}
        )
        coordinator = self.coordinator(request)
        coordinator._token_retry_at = 90
        await coordinator._ensure_valid_token()
        self.assertTrue(request.released)
        data = coordinator.hass.config_entries.async_update_entry.call_args.kwargs["data"]
        self.assertEqual(data["access_token"], "test-access")
        self.assertEqual(data["refresh_token"], "test-new")
        self.assertEqual(data["expires_at"], 4600)
        self.assertEqual(coordinator._token_retry_at, 0)

    async def test_malformed_success_is_retryable_without_token_updates(self):
        """Malformed replies are server failures, not proof of invalid credentials."""
        for data in (
            {},
            [],
            {"access_token": ""},
            {"access_token": "test", "expires_in": "bad"},
            {"access_token": "test", "refresh_token": 123},
        ):
            with self.subTest(data=data):
                request = Request(200, data)
                coordinator = self.coordinator(request)
                with self.assertRaises(UpdateFailed):
                    await coordinator._ensure_valid_token()
                self.assertTrue(request.released)
                coordinator.hass.config_entries.async_update_entry.assert_not_called()

    async def test_success_without_rotation_keeps_existing_refresh_token(self):
        """The optional refresh token must not replace a valid token with None."""
        request = Request(200, {"access_token": "test-access", "refresh_token": None})
        coordinator = self.coordinator(request)
        await coordinator._ensure_valid_token()
        data = coordinator.hass.config_entries.async_update_entry.call_args.kwargs["data"]
        self.assertEqual(data["refresh_token"], "test-refresh")

    async def test_transport_and_json_failures_redact_details(self):
        """Network and decoding errors are retryable and do not expose their text."""
        for error in (
            aiohttp.ClientError("private-details"),
            TimeoutError("private-details"),
            ValueError("private-details"),
        ):
            with self.subTest(error=type(error).__name__):
                request = Request(200)
                request.response.json.side_effect = error
                coordinator = self.coordinator(request)
                with self.assertRaises(UpdateFailed) as raised:
                    await coordinator._ensure_valid_token()
                rendered = "".join(traceback.format_exception(raised.exception))
                self.assertNotIn("private-details", rendered)
                self.assertTrue(request.released)

    async def test_cancellation_is_propagated_and_response_released(self):
        """Shutdown cancellation must not become a retry or an auth failure."""
        request = Request(200)
        request.response.json.side_effect = asyncio.CancelledError
        coordinator = self.coordinator(request)
        with self.assertRaises(asyncio.CancelledError):
            await coordinator._ensure_valid_token()
        self.assertTrue(request.released)

    async def test_valid_access_token_skips_refresh(self):
        """An unexpired access token must not be refreshed."""
        coordinator = self.coordinator(Request())
        coordinator.config_entry.data["expires_at"] = 2000
        await coordinator._ensure_valid_token()
        self.post.assert_not_called()

    def test_retry_after_seconds_date_and_invalid_values(self):
        """Accept both HTTP header forms and bound malformed or extreme values."""
        date = format_datetime(datetime.fromtimestamp(1120, UTC), usegmt=True)
        for value, expected in (
            ("120", 120),
            (date, 120),
            (None, 60),
            ("bad", 60),
            ("nan", 60),
            ("inf", 60),
            ("-1", 30),
            ("999999", 900),
        ):
            with self.subTest(value=value):
                self.assertEqual(integration._token_retry_delay(value), expected)
