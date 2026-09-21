"""Daily job (subscription-housekeeping CronJob, charts/todira) — actually stops Takbull's
recurring engine for a user who cancelled once their already-paid-for period really ends.

website/main.py's /account/cancel-subscription deliberately does NOT call Takbull's
CancelSubscription API at click time (see that route's own comment: Takbull has no documented
"un-cancel" counterpart, so calling it immediately would make /account/resume-subscription unable
to actually resume anything). This is the other half of that design: once paid_until has actually
passed for a user who still has cancel_at_period_end=True, the recurring order is genuinely over —
call Takbull's CancelSubscription for real now, then clear takbull_subscription_uniqid so /account
stops showing an "active subscription" a renewal charge could otherwise still arrive for.

Deliberately idempotent / safe to re-run: a user only matches the query below while
takbull_subscription_uniqid is still set, so a row already cleared (this job's own prior run, or a
fresh subscription created since) never gets processed twice.
"""
from __future__ import annotations

import logging

import takbull_client
from sqlalchemy import func, select
from todira_common.db import get_session
from todira_common.models import User

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def run_once() -> None:
    if not takbull_client.recurring_api_configured():
        logger.info("Takbull recurring API not configured — nothing to do")
        return

    with get_session() as session:
        users = list(
            session.scalars(
                select(User).where(
                    User.cancel_at_period_end.is_(True),
                    User.takbull_subscription_uniqid.is_not(None),
                    User.paid_until.is_not(None),
                    User.paid_until < func.now(),
                )
            )
        )
        logger.info("Found %d cancelled subscription(s) past paid_until to actually cancel", len(users))
        for user in users:
            uniqid = user.takbull_subscription_uniqid
            ok = takbull_client.cancel_subscription(uniqid)
            if ok:
                logger.info("Cancelled Takbull subscription uniqid=%s for user_id=%s", uniqid, user.id)
            else:
                logger.error(
                    "Takbull CancelSubscription failed for uniqid=%s (user_id=%s) — will retry "
                    "on the next run, takbull_subscription_uniqid left set",
                    uniqid, user.id,
                )
                continue
            user.takbull_subscription_uniqid = None
        session.commit()


if __name__ == "__main__":
    run_once()
