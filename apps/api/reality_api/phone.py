"""Twilio Verify transport for real SMS possession checks.

Only Twilio decides whether a code is approved. Reality never generates,
logs, stores, or compares an SMS code locally.
"""

from __future__ import annotations

import re

import httpx

from .config import Settings


class PhoneVerificationError(RuntimeError):
    """Provider request failed or its response was malformed."""


class TwilioPhoneVerifier:
    """Small, bounded HTTP client for Twilio Verify v2."""

    def __init__(self, settings: Settings) -> None:
        account = settings.twilio_account_sid
        token = settings.twilio_auth_token
        service = settings.twilio_verify_service_sid
        if not account or not token or not service:
            raise PhoneVerificationError("SMS verification is not configured")
        if not re.fullmatch(r"AC[0-9a-fA-F]{32}", account) or not re.fullmatch(
            r"VA[0-9a-fA-F]{32}", service
        ):
            raise PhoneVerificationError("Twilio account or Verify service SID is invalid")
        self._account = account
        self._token = token
        self._base = f"https://verify.twilio.com/v2/Services/{service}"

    def start(self, phone: str) -> None:
        response = self._post("Verifications", {"To": phone, "Channel": "sms"})
        if response.get("status") != "pending":
            raise PhoneVerificationError("SMS provider did not accept the verification request")

    def check(self, phone: str, code: str) -> bool:
        response = self._post("VerificationCheck", {"To": phone, "Code": code})
        return response.get("status") == "approved"

    def _post(self, resource: str, data: dict[str, str]) -> dict[str, object]:
        try:
            with httpx.Client(timeout=8.0) as client:
                response = client.post(
                    f"{self._base}/{resource}",
                    data=data,
                    auth=(self._account, self._token),
                )
                if resource == "VerificationCheck" and response.status_code == 404:
                    return {"status": "expired"}
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise PhoneVerificationError("SMS provider request failed") from error
        if not isinstance(payload, dict):
            raise PhoneVerificationError("SMS provider returned an invalid response")
        return payload
