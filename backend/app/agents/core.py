"""Core AI Agents implementation (§6 Phase 9).

Agents:
1. Monitor Agent: Scheduled hourly to inspect promises, surfacing due today & overdue tasks.
2. Briefing Agent: Daily morning brief (spoken & written) precomputed before shop opening.
3. Reminder-Drafter Agent: Generates fixed polite reminder drafts with code-computed numbers.
4. Insight Agent: Answers ad-hoc shopkeeper analytical questions through read-only tools.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from app.agents.models import (
    AgentTask,
    AgentTaskType,
    DailyBriefing,
    ReminderDraft,
)
from app.compliance.agent_guardrails import (
    check_banned_phrases,
    is_within_quiet_hours,
)
from app.storage.encryption import EncryptionService
from app.storage.ledger_service import LedgerService
from app.storage.models import Customer
from app.storage.query_service import QueryService
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class MonitorAgent:
    """Scheduled hourly agent inspecting promises (§6 Phase 9)."""

    def __init__(self, session: AsyncSession, enc_service: EncryptionService):
        self.session = session
        self.enc = enc_service
        self.qs = QueryService(session, encryption_service=enc_service)

    async def run(self, shop_id: str, as_of: date | None = None) -> list[AgentTask]:
        """Scan due and overdue promises and create actionable tasks for the shopkeeper."""
        today = as_of or date.today()
        tasks: list[AgentTask] = []

        # 1. Inspect promises due today
        dues = await self.qs.get_due_promises(shop_id, target_date=today)
        for d in dues:
            amt_rs = d.remaining_paise // 100
            tasks.append(
                AgentTask(
                    id=str(uuid.uuid4()),
                    shop_id=shop_id,
                    task_type=AgentTaskType.PROMISE_DUE_TODAY,
                    title=f"{d.customer_name} payment due today",
                    description=f"{d.customer_name}'s ₹{amt_rs} promise is due today.",
                    customer_id=d.customer_id,
                    customer_name=d.customer_name,
                    amount_paise=d.remaining_paise,
                )
            )

        # 2. Inspect overdue promises
        overdues = await self.qs.get_overdue_promises(shop_id, today=today)
        for o in overdues:
            amt_rs = o.remaining_paise // 100
            tasks.append(
                AgentTask(
                    id=str(uuid.uuid4()),
                    shop_id=shop_id,
                    task_type=AgentTaskType.PROMISE_OVERDUE,
                    title=f"{o.customer_name} payment overdue",
                    description=f"{o.customer_name} had a ₹{amt_rs} promise due on {o.due_date}.",
                    customer_id=o.customer_id,
                    customer_name=o.customer_name,
                    amount_paise=o.remaining_paise,
                )
            )

        return tasks


class BriefingAgent:
    """Precomputes morning spoken and written briefings for the shopkeeper (§6 Phase 9)."""

    def __init__(self, session: AsyncSession, enc_service: EncryptionService):
        self.session = session
        self.enc = enc_service
        self.qs = QueryService(session, encryption_service=enc_service)

    async def generate_briefing(
        self,
        shop_id: str,
        target_date: date | None = None,
        language: str = "hi-IN",
    ) -> DailyBriefing:
        """Precompute morning brief from yesterday's totals and today's dues."""
        today = target_date or date.today()

        # Compute today's due promises
        dues = await self.qs.get_due_promises(shop_id, target_date=today)
        overdues = await self.qs.get_overdue_promises(shop_id, today=today)

        # Period summary for today so far
        summary = await self.qs.get_period_summary(shop_id, today, today, period="today")

        cr_rs = summary.credit_paise // 100
        pay_rs = summary.payment_paise // 100
        n_due = len(dues)
        n_overdue = len(overdues)

        if language.startswith("en"):
            spoken = (
                f"Good morning. Today you have {n_due} payment{'s' if n_due != 1 else ''} due, "
                f"and {n_overdue} overdue. Yesterday's credit was ₹{cr_rs}."
            )
            written = (
                f"Daily Briefing ({today.isoformat()}):\n"
                f"- Payments due today: {n_due}\n"
                f"- Overdue promises: {n_overdue}\n"
                f"- Total credit given: ₹{cr_rs}\n"
                f"- Total payment received: ₹{pay_rs}"
            )
        else:
            spoken = (
                f"Namaste. Aaj {n_due} payment aane baaki hain, aur {n_overdue} overdue hain. "
                f"Kripya list check kar lein."
            )
            written = (
                f"Subah ka Hisaab ({today.isoformat()}):\n"
                f"- Aaj aane wale payment: {n_due}\n"
                f"- Overdue promises: {n_overdue}\n"
                f"- Kul udhaar: ₹{cr_rs}\n"
                f"- Kul jama: ₹{pay_rs}"
            )

        return DailyBriefing(
            shop_id=shop_id,
            target_date=today,
            spoken_text=spoken,
            written_text=written,
            credit_given_paise=summary.credit_paise,
            payments_received_paise=summary.payment_paise,
            due_today_count=n_due,
            overdue_count=n_overdue,
        )


class ReminderDrafterAgent:
    """Prepares polite reminder drafts without judging or threatening customers (§6 Phase 9)."""

    def __init__(self, session: AsyncSession, enc_service: EncryptionService):
        self.session = session
        self.enc = enc_service
        self.ledger = LedgerService(session, encryption_service=enc_service)

    async def draft_reminder(
        self,
        shop_id: str,
        customer_id: str,
        due_date: date,
        now: datetime | None = None,
        language: str = "hi-IN",
    ) -> ReminderDraft | None:
        """Draft a polite reminder message strictly adhering to safety guardrails."""
        current_time = now or datetime.now()

        # Guardrail 1: Quiet hours check
        if is_within_quiet_hours(current_time):
            # Do not generate drafts during quiet hours
            return None

        # Fetch customer
        stmt = select(Customer).where(Customer.shop_id == shop_id, Customer.id == customer_id)
        res = await self.session.execute(stmt)
        cust = res.scalar_one_or_none()
        if not cust:
            return None

        # Guardrail 2: Opt-in requirement (§6 Phase 9: only opted-in customers)
        if not cust.reminder_opt_in:
            return None

        # Balance check: only draft if there is a positive credit balance
        bal = await self.ledger.get_cached_balance(shop_id, customer_id)
        if bal <= 0:
            return None

        amt_rs = bal // 100
        try:
            cust_name = self.enc.decrypt_text(cust.display_name_enc)
        except Exception:
            cust_name = "[Customer]"

        # Guardrail 3: Polite, neutral phrasing. Zero threats or pressure.
        if language.startswith("en"):
            msg = (
                f"Namaste {cust_name}, this is a polite reminder that an amount of "
                f"₹{amt_rs} is due on {due_date.isoformat()}. Thank you for your continued support."
            )
        else:
            msg = (
                f"Namaste {cust_name} ji, aapka ₹{amt_rs} ka hisaab {due_date.isoformat()} "
                f"tak baaki hai. Suvidha anusar jama karwa dein. Dhanyawad."
            )

        # Guardrail 4: Verify against banned phrases
        banned = check_banned_phrases(msg)
        if banned:
            raise ValueError(f"Banned phrase detected in template: {banned}")

        phone = self.enc.decrypt_text(cust.phone_enc) if cust.phone_enc else "0000000000"

        return ReminderDraft(
            id=str(uuid.uuid4()),
            shop_id=shop_id,
            customer_id=customer_id,
            customer_name=cust_name,
            phone=phone,
            amount_paise=bal,
            due_date=due_date,
            message_text=msg,
            opted_in=cust.reminder_opt_in,
            status="PENDING_APPROVAL",  # Always requires shopkeeper approval
        )


class InsightAgent:
    """Answers shopkeeper analytical questions through narrow read-only tools (§6 Phase 9)."""

    def __init__(self, session: AsyncSession, enc_service: EncryptionService):
        self.session = session
        self.enc = enc_service
        self.qs = QueryService(session, encryption_service=enc_service)

    async def answer_inquiry(self, shop_id: str, question: str) -> dict[str, Any]:
        """Process insight inquiries through deterministic read-only query tools."""
        today = date.today()
        lowered = question.lower()

        if "udhaar" in lowered or "credit" in lowered:
            summary = await self.qs.get_period_summary(shop_id, today, today, period="today")
            return {
                "topic": "credit_summary",
                "credit_rupees": summary.credit_paise / 100.0,
                "answer": f"Aaj ka kul udhaar ₹{summary.credit_paise // 100} hai.",
            }
        elif "debtor" in lowered or "baaki" in lowered:
            debtors = await self.qs.get_top_debtors(shop_id, limit=3)
            return {
                "topic": "top_debtors",
                "debtors": [
                    {"name": d.customer_name, "rupees": d.balance_paise / 100.0} for d in debtors
                ],
                "answer": f"{len(debtors)} customers ka udhaar baaki hai.",
            }
        else:
            return {
                "topic": "general",
                "answer": "Aap udhaar ya jama ke baare mein hisaab pooch sakte hain.",
            }
