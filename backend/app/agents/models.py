"""Domain models and storage structures for AI agents (§6 Phase 9)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum


class AgentTaskType(str, Enum):
    PROMISE_DUE_TODAY = "PROMISE_DUE_TODAY"
    PROMISE_OVERDUE = "PROMISE_OVERDUE"
    DAILY_BRIEFING = "DAILY_BRIEFING"
    REMINDER_DRAFT = "REMINDER_DRAFT"
    INSIGHT = "INSIGHT"


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSED = "PROCESSED"
    DISMISSED = "DISMISSED"


@dataclass
class AgentTask:
    id: str
    shop_id: str
    task_type: AgentTaskType
    title: str
    description: str
    customer_id: str | None = None
    customer_name: str | None = None
    amount_paise: int = 0
    status: TaskStatus = TaskStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ReminderDraft:
    id: str
    shop_id: str
    customer_id: str
    customer_name: str
    phone: str
    amount_paise: int
    due_date: date
    message_text: str
    opted_in: bool
    status: str = "PENDING_APPROVAL"  # Outbound messages strictly require approval (§6 Phase 9)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class DailyBriefing:
    shop_id: str
    target_date: date
    spoken_text: str
    written_text: str
    credit_given_paise: int
    payments_received_paise: int
    due_today_count: int
    overdue_count: int
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
