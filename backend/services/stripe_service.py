"""
StripeService — Checkout, Portal, and webhook event handling.

Flat subscriptions only (no metered billing). All Stripe API calls are
synchronous (stripe-python SDK) wrapped in run_in_executor where async
context is needed; for now they execute in the event loop directly since
stripe-python is lightweight and tests mock them.
"""

from __future__ import annotations

import uuid as uuid_mod
from datetime import datetime, timezone
from typing import Optional

import stripe
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.db.models import Subscription, User
from backend.logging.my_logger import get_logger

logger = get_logger(__name__)


# Maps tier names to the corresponding Stripe Price ID (lambda defers read until runtime)
TIER_TO_PRICE: dict[str, str] = {}


def _get_price_id(tier: str) -> str:
    """Return the Stripe Price ID for the given tier."""
    if tier == "individual":
        return settings.stripe_individual_price_id
    if tier == "team":
        return settings.stripe_team_price_id
    raise ValueError(f"No Stripe price configured for tier: {tier!r}")


def _now() -> datetime:
    return datetime.now(timezone.utc)


class StripeService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        stripe.api_key = settings.stripe_secret_key

    # ── Public: Session creation ─────────────────────────────────────

    async def create_checkout_session(self, user: User, tier: str, return_url: str) -> str:
        """Create a Stripe Checkout Session for upgrading to *tier*.

        Returns the hosted Checkout URL. Creates a Stripe Customer for the
        user if one does not already exist.
        """
        customer_id = await self._ensure_stripe_customer(user)
        price_id = _get_price_id(tier)

        session = stripe.checkout.Session.create(
            customer=customer_id,
            payment_method_types=["card"],
            line_items=[{"price": price_id, "quantity": 1}],
            mode="subscription",
            success_url=return_url + "?checkout=success",
            cancel_url=return_url + "?checkout=cancel",
            metadata={"tier": tier, "user_id": str(user.id)},
        )
        return session.url

    async def create_portal_session(self, user: User, return_url: str) -> str:
        """Create a Stripe Billing Portal session for managing an existing subscription.

        Returns the portal URL.
        """
        session = stripe.billing_portal.Session.create(
            customer=user.stripe_customer_id,
            return_url=return_url,
        )
        return session.url

    # ── Public: Webhook event handlers ──────────────────────────────

    async def handle_checkout_completed(self, session_data: dict) -> None:
        """Handle checkout.session.completed — activate subscription."""
        customer_id: str = session_data.get("customer", "")
        subscription_id: str = session_data.get("subscription", "")
        metadata: dict = session_data.get("metadata", {})

        tier: str = metadata.get("tier", "individual")
        user_id_str: str = metadata.get("user_id", "")

        user = await self._find_user(user_id=user_id_str, customer_id=customer_id)
        if user is None:
            logger.warning("handle_checkout_completed: user not found customer=%s user_id=%s", customer_id, user_id_str)
            return

        user.tier = tier
        if customer_id and not user.stripe_customer_id:
            user.stripe_customer_id = customer_id

        await self._upsert_subscription(
            user=user,
            tier=tier,
            stripe_subscription_id=subscription_id,
            stripe_customer_id=customer_id,
            status="active",
        )
        await self._db.commit()
        logger.info("handle_checkout_completed: user=%s upgraded to tier=%s", user.id, tier)

    async def handle_subscription_updated(self, sub_data: dict) -> None:
        """Handle customer.subscription.updated — sync status and period dates."""
        stripe_sub_id: str = sub_data.get("id", "")
        status: str = sub_data.get("status", "active")
        cancel_at_period_end: bool = sub_data.get("cancel_at_period_end", False)

        period_start: Optional[datetime] = None
        period_end: Optional[datetime] = None
        if sub_data.get("current_period_start"):
            period_start = datetime.fromtimestamp(sub_data["current_period_start"], tz=timezone.utc)
        if sub_data.get("current_period_end"):
            period_end = datetime.fromtimestamp(sub_data["current_period_end"], tz=timezone.utc)

        result = await self._db.execute(
            select(Subscription).where(Subscription.stripe_subscription_id == stripe_sub_id)
        )
        sub = result.scalar_one_or_none()
        if sub is None:
            logger.warning("handle_subscription_updated: subscription not found stripe_sub_id=%s", stripe_sub_id)
            return

        sub.status = status
        sub.cancel_at_period_end = cancel_at_period_end
        if period_start:
            sub.current_period_start = period_start
        if period_end:
            sub.current_period_end = period_end

        await self._db.commit()
        logger.info("handle_subscription_updated: stripe_sub_id=%s status=%s", stripe_sub_id, status)

    async def handle_subscription_deleted(self, sub_data: dict) -> None:
        """Handle customer.subscription.deleted — downgrade user to free tier."""
        customer_id: str = sub_data.get("customer", "")
        stripe_sub_id: str = sub_data.get("id", "")

        user = await self._find_user(customer_id=customer_id)
        if user is None:
            logger.warning("handle_subscription_deleted: user not found customer=%s", customer_id)
            return

        user.tier = "free"

        result = await self._db.execute(
            select(Subscription).where(
                Subscription.user_id == user.id,
                Subscription.stripe_subscription_id == stripe_sub_id,
            )
        )
        sub = result.scalar_one_or_none()
        if sub is not None:
            sub.tier = "free"
            sub.status = "canceled"

        await self._db.commit()
        logger.info("handle_subscription_deleted: user=%s downgraded to free", user.id)

    async def handle_payment_failed(self, invoice_data: dict) -> None:
        """Handle invoice.payment_failed — mark subscription past_due."""
        customer_id: str = invoice_data.get("customer", "")
        stripe_sub_id: str = invoice_data.get("subscription", "")

        result = await self._db.execute(
            select(Subscription).where(
                Subscription.stripe_customer_id == customer_id,
                Subscription.stripe_subscription_id == stripe_sub_id,
            )
        )
        sub = result.scalar_one_or_none()
        if sub is None:
            logger.warning("handle_payment_failed: subscription not found customer=%s sub=%s", customer_id, stripe_sub_id)
            return

        sub.status = "past_due"
        await self._db.commit()
        logger.info("handle_payment_failed: sub=%s marked past_due", stripe_sub_id)

    async def handle_invoice_paid(self, invoice_data: dict) -> None:
        """Handle invoice.paid — clear past_due status, restore to active."""
        stripe_sub_id: str = invoice_data.get("subscription", "")

        result = await self._db.execute(
            select(Subscription).where(Subscription.stripe_subscription_id == stripe_sub_id)
        )
        sub = result.scalar_one_or_none()
        if sub is None:
            logger.warning("handle_invoice_paid: subscription not found stripe_sub_id=%s", stripe_sub_id)
            return

        sub.status = "active"
        await self._db.commit()
        logger.info("handle_invoice_paid: sub=%s restored to active", stripe_sub_id)

    # ── Private helpers ──────────────────────────────────────────────

    async def _ensure_stripe_customer(self, user: User) -> str:
        """Return the existing Stripe Customer ID, or create one and persist it."""
        if user.stripe_customer_id:
            return user.stripe_customer_id

        customer = stripe.Customer.create(
            email=user.email,
            metadata={"user_id": str(user.id)},
        )
        user.stripe_customer_id = customer.id
        await self._db.commit()
        await self._db.refresh(user)
        return customer.id

    async def _find_user(
        self,
        *,
        user_id: Optional[str] = None,
        customer_id: Optional[str] = None,
    ) -> Optional[User]:
        """Look up a user by UUID string or Stripe Customer ID."""
        if user_id:
            try:
                uid = uuid_mod.UUID(user_id)
            except (ValueError, AttributeError):
                pass
            else:
                result = await self._db.execute(select(User).where(User.id == uid))
                user = result.scalar_one_or_none()
                if user is not None:
                    return user

        if customer_id:
            result = await self._db.execute(
                select(User).where(User.stripe_customer_id == customer_id)
            )
            return result.scalar_one_or_none()

        return None

    async def _upsert_subscription(
        self,
        *,
        user: User,
        tier: str,
        stripe_subscription_id: str,
        stripe_customer_id: str,
        status: str = "active",
        current_period_start: Optional[datetime] = None,
        current_period_end: Optional[datetime] = None,
    ) -> Subscription:
        """Create or update the Subscription row for this user."""
        result = await self._db.execute(
            select(Subscription).where(Subscription.user_id == user.id)
        )
        sub = result.scalar_one_or_none()

        if sub is None:
            sub = Subscription(
                id=uuid_mod.uuid4(),
                user_id=user.id,
                tier=tier,
                stripe_customer_id=stripe_customer_id,
                stripe_subscription_id=stripe_subscription_id,
                status=status,
                current_period_start=current_period_start,
                current_period_end=current_period_end,
            )
            self._db.add(sub)
        else:
            sub.tier = tier
            sub.stripe_customer_id = stripe_customer_id
            sub.stripe_subscription_id = stripe_subscription_id
            sub.status = status
            if current_period_start:
                sub.current_period_start = current_period_start
            if current_period_end:
                sub.current_period_end = current_period_end

        return sub
