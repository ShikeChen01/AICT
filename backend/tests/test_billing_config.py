"""Tests for billing configuration."""
import os
import pytest


def test_settings_has_stripe_fields():
    from backend.config import Settings
    s = Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        stripe_secret_key="sk_test_xxx",
        stripe_publishable_key="pk_test_xxx",
    )
    assert s.stripe_secret_key == "sk_test_xxx"
    assert s.stripe_publishable_key == "pk_test_xxx"
    assert s.stripe_webhook_secret == ""
    assert s.stripe_individual_price_id == ""
    assert s.stripe_team_price_id == ""
    assert s.tier_enforcement_enabled is False


def test_settings_stripe_defaults_empty():
    from backend.config import Settings
    s = Settings(database_url="sqlite+aiosqlite:///:memory:")
    assert s.stripe_secret_key == ""
    assert s.tier_enforcement_enabled is False
