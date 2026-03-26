"""Tests for OAuth service — state tokens, flow logic."""

import time
import json
import hashlib
import hmac

import pytest

from backend.services.oauth_service import (
    create_state_token,
    verify_state_token,
    _hmac_key,
)


class TestStateTokens:
    def test_create_and_verify_roundtrip(self):
        token = create_state_token("login")
        payload = verify_state_token(token)
        assert payload is not None
        assert payload["flow"] == "login"
        assert "nonce" in payload
        assert "exp" in payload

    def test_connect_flow_type(self):
        token = create_state_token("connect")
        payload = verify_state_token(token)
        assert payload["flow"] == "connect"

    def test_tampered_token_rejected(self):
        token = create_state_token("login")
        tampered = token[:-1] + ("a" if token[-1] != "a" else "b")
        with pytest.raises(ValueError, match="signature invalid"):
            verify_state_token(tampered)

    def test_expired_token_rejected(self):
        # Build a token with an already-expired exp using the same hex|sig format
        payload = {
            "flow": "login",
            "nonce": "deadbeef" * 4,
            "exp": int(time.time()) - 1,
        }
        payload_json = json.dumps(payload, separators=(",", ":"))
        payload_bytes = payload_json.encode()
        sig = hmac.new(_hmac_key(), payload_bytes, hashlib.sha256).hexdigest()
        payload_hex = payload_bytes.hex()
        expired_token = f"{payload_hex}|{sig}"
        with pytest.raises(ValueError, match="expired"):
            verify_state_token(expired_token)

    def test_malformed_token_rejected(self):
        with pytest.raises(ValueError):
            verify_state_token("not-a-valid-token")
        with pytest.raises(ValueError):
            verify_state_token("")
        # Three segments — after split("|", 1) the sig part would be "b|c",
        # which won't match the HMAC, so it raises signature invalid.
        with pytest.raises(ValueError):
            verify_state_token("a|b|c")
