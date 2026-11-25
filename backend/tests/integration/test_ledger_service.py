"""Integration tests against real PostgreSQL 16 verifying ledger invariants (§3, §5.1, §5.6)."""

import time
import uuid
from datetime import date

import asyncpg
import pytest
from app.core.config import get_settings
from app.domain.enums import Direction
from app.storage.db import init_tables
from app.storage.encryption import EncryptionService
from app.storage.ledger_service import LedgerService
from app.storage.models import Shop
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool


@pytest.fixture
async def session() -> AsyncSession:
    db_url = get_settings().database_url
    test_engine = create_async_engine(db_url, poolclass=NullPool)
    await init_tables(test_engine)
    factory = async_sessionmaker(test_engine, expire_on_commit=False, class_=AsyncSession)
    async with factory() as sess:
        yield sess
    await test_engine.dispose()


@pytest.fixture
def enc_service() -> EncryptionService:
    return EncryptionService()


@pytest.mark.asyncio
async def test_single_transaction_commit_and_balance_cache(
    session: AsyncSession,
    enc_service: EncryptionService,
) -> None:
    shop_id = str(uuid.uuid4())
    shop = Shop(id=shop_id, name="Test Kirana", language="hi-IN")
    session.add(shop)
    await session.commit()

    service = LedgerService(session, encryption_service=enc_service)

    # 1. Credit 340 to Ramesh (34000 paise)
    res1 = await service.record_event(
        shop_id=shop_id,
        customer_name="Ramesh",
        amount_paise=34000,
        direction=Direction.CREDIT_GIVEN,
        occurred_on=date.today(),
        idempotency_key=str(uuid.uuid4()),
        note="Initial credit",
    )
    await session.commit()
    assert res1.is_duplicate is False
    assert res1.new_balance_paise == 34000

    # 2. Payment 200 from Ramesh (20000 paise)
    res2 = await service.record_event(
        shop_id=shop_id,
        customer_name="Ramesh",
        amount_paise=20000,
        direction=Direction.PAYMENT_RECEIVED,
        occurred_on=date.today(),
        idempotency_key=str(uuid.uuid4()),
    )
    await session.commit()
    assert res2.is_duplicate is False
    assert res2.new_balance_paise == 14000

    # 3. Verify balance cache == replay of event log
    cached_bal = await service.get_cached_balance(shop_id, res1.customer_id)
    replayed_bal = await service.replay_customer_balance(shop_id, res1.customer_id)
    assert cached_bal == 14000
    assert replayed_bal == 14000
    assert cached_bal == replayed_bal


@pytest.mark.asyncio
async def test_idempotent_duplicate_handling(
    session: AsyncSession,
    enc_service: EncryptionService,
) -> None:
    shop_id = str(uuid.uuid4())
    shop = Shop(id=shop_id, name="Idempotent Kirana", language="hi-IN")
    session.add(shop)
    await session.commit()

    service = LedgerService(session, encryption_service=enc_service)
    idem_key = "test_idem_key_123"

    # First attempt
    res1 = await service.record_event(
        shop_id=shop_id,
        customer_name="Suresh",
        amount_paise=50000,
        direction=Direction.CREDIT_GIVEN,
        occurred_on=date.today(),
        idempotency_key=idem_key,
    )
    await session.commit()
    assert res1.is_duplicate is False
    assert res1.new_balance_paise == 50000

    # Second attempt with identical idempotency_key
    res2 = await service.record_event(
        shop_id=shop_id,
        customer_name="Suresh",
        amount_paise=50000,
        direction=Direction.CREDIT_GIVEN,
        occurred_on=date.today(),
        idempotency_key=idem_key,
    )
    assert res2.is_duplicate is True
    assert res2.new_balance_paise == 50000
    assert res2.event_id == res1.event_id

    # Verify balance did NOT double
    bal = await service.get_cached_balance(shop_id, res1.customer_id)
    assert bal == 50000


@pytest.mark.asyncio
async def test_encryption_at_rest_plaintext_check(
    session: AsyncSession,
    enc_service: EncryptionService,
) -> None:
    shop_id = str(uuid.uuid4())
    shop = Shop(id=shop_id, name="Secure Kirana", language="hi-IN")
    session.add(shop)
    await session.commit()

    service = LedgerService(session, encryption_service=enc_service)
    customer_name = "Vikram Sharma Sabziwala"
    amount_paise = 250000
    note_text = "Urgent counter credit for Diwali goods"

    res = await service.record_event(
        shop_id=shop_id,
        customer_name=customer_name,
        amount_paise=amount_paise,
        direction=Direction.CREDIT_GIVEN,
        occurred_on=date.today(),
        idempotency_key=str(uuid.uuid4()),
        note=note_text,
    )
    await session.commit()

    # Query raw database row directly using asyncpg bypassing SQLAlchemy
    conn = await asyncpg.connect("postgresql://postgres:postgres@localhost:5432/voice_khata")
    try:
        # Check customer table
        cust_row = await conn.fetchrow("SELECT * FROM customers WHERE id = $1", res.customer_id)
        assert cust_row is not None
        assert "Vikram" not in cust_row["display_name_enc"]
        assert "Sharma" not in cust_row["display_name_enc"]

        # Check ledger_events table
        event_row = await conn.fetchrow("SELECT * FROM ledger_events WHERE id = $1", res.event_id)
        assert event_row is not None
        assert "250000" not in event_row["amount_paise_enc"]
        assert "Diwali" not in (event_row["note_enc"] or "")
        assert "Urgent" not in (event_row["note_enc"] or "")
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_export_and_delete_all(
    session: AsyncSession,
    enc_service: EncryptionService,
) -> None:
    shop_id = str(uuid.uuid4())
    shop = Shop(id=shop_id, name="Export Kirana", language="hi-IN")
    session.add(shop)
    await session.commit()

    service = LedgerService(session, encryption_service=enc_service)
    await service.record_event(
        shop_id=shop_id,
        customer_name="Anita",
        amount_paise=80000,
        direction=Direction.PAYMENT_RECEIVED,
        occurred_on=date.today(),
        idempotency_key=str(uuid.uuid4()),
    )
    await session.commit()

    # 1. Export data
    exported = await service.export_all_data(shop_id)
    assert len(exported["customers"]) == 1
    assert exported["customers"][0]["display_name"] == "Anita"
    assert len(exported["events"]) == 1
    assert exported["events"][0]["amount_paise"] == 80000

    # 2. Delete all data
    await service.delete_all_data(shop_id)

    # 3. Verify empty
    exported_after = await service.export_all_data(shop_id)
    assert len(exported_after["customers"]) == 0
    assert len(exported_after["events"]) == 0


@pytest.mark.asyncio
async def test_commit_latency_benchmark(
    enc_service: EncryptionService,
) -> None:
    # §4.2 target: DB commit of an entry <= 30 ms p95 with warm pooled connection (§4.3.2)
    db_url = get_settings().database_url
    bench_engine = create_async_engine(db_url, pool_size=5, max_overflow=10)
    factory = async_sessionmaker(bench_engine, expire_on_commit=False, class_=AsyncSession)
    shop_id = str(uuid.uuid4())

    try:
        async with factory() as session:
            shop = Shop(id=shop_id, name="Perf Kirana", language="hi-IN")
            session.add(shop)
            await session.commit()

            service = LedgerService(session, encryption_service=enc_service)

            # Warmup connection pool and customer caches
            for w in range(10):
                await service.record_event(
                    shop_id=shop_id,
                    customer_name=f"WarmupCustomer_{w % 3}",
                    amount_paise=10000,
                    direction=Direction.CREDIT_GIVEN,
                    occurred_on=date.today(),
                    idempotency_key=f"warmup_{w}",
                )
                await session.commit()

            latencies: list[float] = []
            for i in range(50):
                t0 = time.perf_counter()
                await service.record_event(
                    shop_id=shop_id,
                    customer_name=f"Customer_{i % 5}",
                    amount_paise=10000 + i * 100,
                    direction=Direction.CREDIT_GIVEN,
                    occurred_on=date.today(),
                    idempotency_key=f"bench_key_{i}",
                )
                await session.commit()
                dt_ms = (time.perf_counter() - t0) * 1000.0
                latencies.append(dt_ms)

            latencies.sort()
            p50 = latencies[len(latencies) // 2]
            p95 = latencies[int(len(latencies) * 0.95)]
            print(
                f"\n[DB COMMIT BENCHMARK] P50: {p50:.2f}ms, P95: {p95:.2f}ms, "
                f"Min: {min(latencies):.2f}ms"
            )
            assert p95 <= 30.0
    finally:
        await bench_engine.dispose()


@pytest.mark.asyncio
async def test_promise_creation_and_allocation(
    session: AsyncSession,
    enc_service: EncryptionService,
) -> None:
    shop_id = str(uuid.uuid4())
    shop = Shop(id=shop_id, name="Promise Kirana", language="hi-IN")
    session.add(shop)
    await session.commit()

    service = LedgerService(session, encryption_service=enc_service)

    # 1. Credit 2000 to Ramesh (200000 paise)
    res_credit = await service.record_event(
        shop_id=shop_id,
        customer_name="Ramesh",
        amount_paise=200000,
        direction=Direction.CREDIT_GIVEN,
        occurred_on=date.today(),
        idempotency_key=str(uuid.uuid4()),
    )
    await session.commit()
    cust_id = res_credit.customer_id

    # 2. Create promise for Ramesh: 2000 due next week
    due = date.today()
    prom = await service.create_promise(
        shop_id=shop_id,
        customer_id=cust_id,
        due_date=due,
        amount_paise=200000,
        source_event_id=res_credit.event_id,
    )
    await session.commit()
    assert prom.id is not None

    # Check promises before payment -> OPEN, remaining 200000
    promises = await service.get_customer_promises(shop_id, cust_id)
    assert len(promises) == 1
    assert promises[0].status.value == "OPEN"
    assert promises[0].remaining_paise == 200000

    # 3. Partial payment of 800 (80000 paise) with note
    await service.record_event(
        shop_id=shop_id,
        customer_name="Ramesh",
        amount_paise=80000,
        direction=Direction.PAYMENT_RECEIVED,
        occurred_on=date.today(),
        idempotency_key=str(uuid.uuid4()),
        note="salary late aayi",
    )
    await session.commit()

    # Derived promise status should now be PARTIALLY_KEPT, remaining 120000 paise
    promises_after = await service.get_customer_promises(shop_id, cust_id)
    assert len(promises_after) == 1
    assert promises_after[0].status.value == "PARTIALLY_KEPT"
    assert promises_after[0].allocated_paise == 80000
    assert promises_after[0].remaining_paise == 120000
