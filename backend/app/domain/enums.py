"""Core domain enumerations for ledger transactions and voice intents."""

from enum import Enum


class Direction(str, Enum):
    CREDIT_GIVEN = "CREDIT_GIVEN"  # Udhaar given to customer
    PAYMENT_RECEIVED = "PAYMENT_RECEIVED"  # Payment received from customer (jama)
    AMENDED = "AMENDED"  # Correction of earlier transaction
    VOIDED = "VOIDED"  # Undo / removal of transaction


class Intent(str, Enum):
    RECORD = "record"  # Record udhaar or payment
    QUERY = "query"  # Inquire balance or period totals
    UNDO = "undo"  # Void last entry
    CORRECT = "correct"  # Amend last entry amount/date
    OTHER = "other"  # Out-of-scope or general requests


class PromiseStatus(str, Enum):
    OPEN = "OPEN"
    PARTIALLY_KEPT = "PARTIALLY_KEPT"
    KEPT = "KEPT"
    BROKEN = "BROKEN"
    RESCHEDULED = "RESCHEDULED"
    CANCELLED = "CANCELLED"
