"""Billing request/response schemas."""
from pydantic import BaseModel


class CheckoutSessionRequest(BaseModel):
    tier: str
    return_url: str = "/settings/billing"


class CheckoutSessionResponse(BaseModel):
    checkout_url: str


class PortalSessionRequest(BaseModel):
    return_url: str = "/settings/billing"


class PortalSessionResponse(BaseModel):
    portal_url: str


class SubscriptionResponse(BaseModel):
    tier: str
    status: str
    cancel_at_period_end: bool = False
    current_period_end: str | None = None


class UsageSummaryResponse(BaseModel):
    tier: str
    period_start: str
    period_end: str
    headless_seconds_used: int
    headless_seconds_included: int
    desktop_seconds_used: int
    desktop_seconds_included: int
