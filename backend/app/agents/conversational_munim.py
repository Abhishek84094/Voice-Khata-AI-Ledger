"""Conversational Munim Agent orchestrator (§6 Phase 9, Phase 10).

Translates natural, compound, conversational shopkeeper queries and instructions
into multi-turn actions (adding promises, modifying promises, answering ledger questions)
by querying and updating real-time database state and synthesizing natural conversational
Hindi/Hinglish speech using Groq LLM.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
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
        """Process compound instructions (e.g. promises or business questions)."""
        today = date.today()
        lowered = user_utterance.lower()

        # Check if the user is asking to add/alter/reschedule a promise:
        promise_words = [
            "promise",
            "dega",
            "degi",
            "tariq",
            "tarikh",
            "somwar",
            "mangalwar",
            "budhwar",
            "guruwar",
            "shukrawar",
            "shanivar",
            "ravivar",
            "agle",
            "aayega",
        ]
        action_words = ["add", "likho", "update", "karo", "daalo", "kar do", "rakho", "hai"]
        is_promise_instruction = any(w in lowered for w in promise_words) and any(
            w in lowered for w in action_words
        )

        if is_promise_instruction and self.llm:
            sys = (
                "You are an intelligent Munim assistant at a kirana shop. "
                "The shopkeeper wants to record or update a payment promise.\n"
                "- customer_name: customer name (e.g. Ramesh, Priya)\n"
                "- amount_rupees: amount in rupees if stated, or null\n"
                "- due_day_offset: days from today for promised payment (e.g. 1, 7)\n"
                "- speech_reply: natural response in Hindi confirming the promise.\n"
                "Return JSON with keys: customer_name, amount_rupees, due_day_offset, speech_reply"
            )
            prompt = (
                f'Shopkeeper said: "{user_utterance}" (Today is {today.strftime("%A, %Y-%m-%d")})'
            )
            try:
                res = await self.llm.complete_json(prompt=prompt, system_prompt=sys)
                cust_name = res.get("customer_name")
                amt_rs = res.get("amount_rupees")
                offset = res.get("due_day_offset") or 7
                speech = res.get("speech_reply")

                if cust_name:
                    cust_id, _ = await self.ledger.get_or_create_customer(shop_id, cust_name)
                    amt_paise = int(amt_rs * 100) if amt_rs else None
                    if amt_paise is None:
                        bal = await self.ledger.get_cached_balance(shop_id, cust_id)
                        amt_paise = max(0, bal)

                    due_d = today + timedelta(days=int(offset))
                    await self.ledger.create_promise(
                        shop_id=shop_id,
                        customer_id=cust_id,
                        due_date=due_d,
                        amount_paise=amt_paise,
                    )
                    await self.session.commit()

                    date_str = due_d.strftime("%d %B")
                    default_speech = (
                        f"Theek hai, {cust_name} ki ₹{amt_paise // 100} ki "
                        f"promise {date_str} darj ho gayi."
                    )
                    reply_text = speech or default_speech
                    return {
                        "answer": reply_text,
                        "facts": {
                            "action": "promise_created",
                            "customer": cust_name,
                            "due_date": due_d.isoformat(),
                            "amount_rupees": amt_paise // 100,
                        },
                    }
            except Exception as e:
                logger.warning(f"Promise instruction LLM extraction failed: {e}")

        # General factual inquiry handling
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

        # Fallback deterministic natural response
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
