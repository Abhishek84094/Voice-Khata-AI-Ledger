"""Conversational Munim Agent orchestrator (§6 Phase 9, Phase 10).

Translates natural, compound, conversational shopkeeper queries into multi-turn
answers by querying real-time database state (via QueryService and LedgerService)
and synthesizing natural, human-like conversational Hindi/Hinglish speech using Groq LLM.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from app.core.config import get_settings
from app.storage.encryption import EncryptionService
from app.storage.ledger_service import LedgerService
from app.storage.query_service import QueryService
from app.voice.groq import GroqLLMAdapter
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class ConversationalMunimAgent:
    def __init__(
        self,
        db_session: AsyncSession,
        encryption_service: EncryptionService,
    ) -> None:
        self.session = db_session
        self.enc = encryption_service
        self.qs = QueryService(db_session, encryption_service=encryption_service)
        self.ledger = LedgerService(db_session, encryption_service=encryption_service)

        settings = get_settings()
        self.llm: GroqLLMAdapter | None = None
        if settings.groq_api_key:
            self.llm = GroqLLMAdapter(api_key=settings.groq_api_key)

    async def answer_shopkeeper(
        self,
        shop_id: str,
        user_utterance: str,
        language: str = "hi-IN",
    ) -> dict[str, Any]:
        """Fetch accurate database records and produce a natural, human conversational response."""
        today = date.today()

        # 1. Gather all real-time ledger context for this shop
        summary = await self.qs.get_period_summary(shop_id, today, today, period="today")
        recent_entries = await self.qs.get_recent_entries(shop_id, limit=10)
        due_promises = await self.qs.get_due_promises(shop_id, target_date=today)
        overdue_promises = await self.qs.get_overdue_promises(shop_id)
        top_debtors = await self.qs.get_top_debtors(shop_id, limit=5)

        today_credit_rs = summary.credit_paise // 100
        today_payment_rs = summary.payment_paise // 100

        recent_txs: list[str] = []
        for r in recent_entries:
            if r.occurred_on == today:
                dir_str = "udhaar" if r.direction == "CREDIT_GIVEN" else "jama"
                amt_str = f"₹{r.amount_paise // 100}"
                recent_txs.append(f"- {r.customer_name}: {amt_str} ({dir_str})")

        dues_info = [
            f"- {d.customer_name}: ₹{d.remaining_paise // 100} due today" for d in due_promises
        ]

        overdues_info = [
            f"- {o.customer_name}: ₹{o.remaining_paise // 100} overdue" for o in overdue_promises
        ]

        facts = {
            "today_date": today.isoformat(),
            "today_credit_given_rupees": today_credit_rs,
            "today_payment_received_rupees": today_payment_rs,
            "today_transactions": recent_txs,
            "promises_due_today": dues_info,
            "overdue_promises": overdues_info,
            "top_debtors": [
                f"- {d.customer_name}: ₹{d.balance_paise // 100} pending" for d in top_debtors
            ],
        }

        # 2. If Groq LLM is available, craft a warm, concise, conversational response
        if self.llm:
            system_prompt = (
                "You are an intelligent, friendly, respectful digital Munim (clerk) at a shop. "
                "Rules:\n"
                "1. Answer naturally in warm spoken Hindi/Hinglish (like a trusted partner).\n"
                "2. Strictly use the exact facts and numbers provided. NEVER invent numbers.\n"
                "3. Keep the spoken answer concise and clear (2-3 sentences max).\n"
                "4. Return a JSON object with key 'speech_reply' containing your spoken response."
            )

            txs_block = "\n".join(recent_txs) if recent_txs else "  (Koi nayi entry nahi)"
            dues_block = "\n".join(dues_info) if dues_info else "  (Koi promise aaj due nahi hai)"
            overdues_block = (
                "\n".join(overdues_info) if overdues_info else "  (Koi overdue nahi hai)"
            )

            prompt = (
                f'Shopkeeper asked: "{user_utterance}"\n\n'
                f"Real ledger facts from database:\n"
                f"- Today's total credit given: ₹{today_credit_rs}\n"
                f"- Today's total payments received: ₹{today_payment_rs}\n"
                f"- Today's credit entries by customer:\n{txs_block}\n"
                f"- Promises due today:\n{dues_block}\n"
                f"- Overdue promises:\n{overdues_block}\n\n"
                "Provide a natural conversational speech reply answering the shopkeeper directly."
            )

            try:
                res = await self.llm.complete_json(prompt=prompt, system_prompt=system_prompt)
                reply = res.get("speech_reply")
                if reply:
                    return {
                        "answer": reply,
                        "facts": facts,
                    }
            except Exception as e:
                logger.warning(f"Groq LLM conversational response failed: {e}")

        # Fallback deterministic natural response if LLM call fails or is unavailable
        parts: list[str] = []
        if today_credit_rs > 0:
            parts.append(f"Aaj kul ₹{today_credit_rs} ka udhaar gaya hai.")
            if recent_txs:
                active_names = [
                    f"{r.customer_name} ka ₹{r.amount_paise // 100}"
                    for r in recent_entries
                    if r.occurred_on == today
                ][:3]
                parts.append("Jisme: " + ", ".join(active_names) + ".")
        else:
            parts.append("Aaj koi naya udhaar nahi gaya hai.")

        if dues_info:
            parts.append(f"Aaj {len(due_promises)} customer ka payment due hai.")
        else:
            parts.append("Aaj koi promise due nahi hai.")

        return {
            "answer": " ".join(parts),
            "facts": facts,
        }
