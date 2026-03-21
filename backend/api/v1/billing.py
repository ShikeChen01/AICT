"""
Billing API — subscription status, usage summary, Stripe Checkout/Portal, and webhook.
"""

from __future__ import annotations

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.core.auth import get_current_user
from backend.db.models import Subscription, User
from backend.db.session import get_db
from backend.logging.my_logger import get_logger
from backend.schemas.billing import (
    CheckoutSessionRequest,
    CheckoutSessionResponse,
    PortalSessionRequest,
    PortalSessionResponse,
    SubscriptionResponse,
    UsageSummaryResponse,
)
from backend.services.stripe_service import StripeService
from backend.services.tier_service import TierService

logger = get_logger(__name__)

router = APIRouter(prefix="/billing", tags=["billing"])

_PAID_TIERS = {"individual", "team"}


@router.get("/subscription", response_model=SubscriptionResponse)
async def get_subscription(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SubscriptionResponse:
    """Return the current subscription tier and status for the authenticated user."""
    result = await db.execute(
        select(Subscription).where(Subscription.user_id == current_user.id)
    )
    sub = result.scalar_one_or_none()

    if sub is not None:
        return SubscriptionResponse(
            tier=sub.tier,
            status=sub.status,
            cancel_at_period_end=sub.cancel_at_period_end,
            current_period_end=(
                sub.current_period_end.isoformat() if sub.current_period_end else None
            ),
        )

    # Fall back to User.tier when no Subscription row exists yet
    return SubscriptionResponse(
        tier=current_user.tier,
        status="active",
        cancel_at_period_end=False,
        current_period_end=None,
    )


@router.get("/usage", response_model=UsageSummaryResponse)
async def get_usage(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UsageSummaryResponse:
    """Return sandbox hour usage summary for the current billing period."""
    tier_service = TierService(db)
    summary = await tier_service.get_usage_summary(current_user)
    return UsageSummaryResponse(**summary)


@router.post("/checkout-session", response_model=CheckoutSessionResponse)
async def create_checkout_session(
    body: CheckoutSessionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CheckoutSessionResponse:
    """Create a Stripe Checkout Session for upgrading to a paid tier."""
    if body.tier not in _PAID_TIERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid tier {body.tier!r}. Must be one of: {sorted(_PAID_TIERS)}",
        )

    stripe_service = StripeService(db)
    checkout_url = await stripe_service.create_checkout_session(
        user=current_user,
        tier=body.tier,
        return_url=body.return_url,
    )
    return CheckoutSessionResponse(checkout_url=checkout_url)


@router.post("/portal-session", response_model=PortalSessionResponse)
async def create_portal_session(
    body: PortalSessionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PortalSessionResponse:
    """Create a Stripe Customer Portal session for managing an existing subscription."""
    if not current_user.stripe_customer_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No Stripe customer associated with this account.",
        )

    stripe_service = StripeService(db)
    portal_url = await stripe_service.create_portal_session(
        user=current_user,
        return_url=body.return_url,
    )
    return PortalSessionResponse(portal_url=portal_url)


@router.post("/webhook", include_in_schema=False)
async def stripe_webhook(request: Request) -> dict:
    """Handle Stripe webhook events. Signature is verified; no JWT auth required."""
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.stripe_webhook_secret
        )
    except stripe.SignatureVerificationError as exc:
        logger.warning("Stripe webhook signature verification failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid Stripe signature",
        ) from exc
    except Exception as exc:
        logger.error("Stripe webhook payload error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid webhook payload",
        ) from exc

    event_type: str = event["type"]
    event_data: dict = event["data"]["object"]

    # Each handler gets a fresh session so webhook failures don't affect other requests
    from backend.db.session import AsyncSessionLocal  # noqa: PLC0415

    async with AsyncSessionLocal() as db:
        stripe_service = StripeService(db)

        if event_type == "checkout.session.completed":
            await stripe_service.handle_checkout_completed(event_data)
        elif event_type == "customer.subscription.updated":
            await stripe_service.handle_subscription_updated(event_data)
        elif event_type == "customer.subscription.deleted":
            await stripe_service.handle_subscription_deleted(event_data)
        elif event_type == "invoice.payment_failed":
            await stripe_service.handle_payment_failed(event_data)
        elif event_type == "invoice.paid":
            await stripe_service.handle_invoice_paid(event_data)
        else:
            logger.debug("Unhandled Stripe event type: %s", event_type)

    return {"status": "ok"}
