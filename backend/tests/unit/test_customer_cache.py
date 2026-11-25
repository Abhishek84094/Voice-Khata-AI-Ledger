"""Unit and micro-benchmark tests for in-memory customer resolution cache."""

import time

from app.storage.customer_cache import CachedCustomer, CustomerCache


def test_customer_cache_exact_resolution() -> None:
    cache = CustomerCache()
    c1 = CachedCustomer(id="c1", shop_id="s1", display_name="Ramesh", search_key="ramesh")
    c2 = CachedCustomer(id="c2", shop_id="s1", display_name="Suresh", search_key="suresh")
    cache.load_shop_customers("s1", [c1, c2])

    match, amb = cache.resolve_customer("s1", "Ramesh")
    assert match is not None
    assert match.id == "c1"
    assert len(amb) == 0


def test_customer_cache_devanagari_cross_script() -> None:
    cache = CustomerCache()
    c1 = CachedCustomer(id="c1", shop_id="s1", display_name="रमेश", search_key="ramesh")
    cache.load_shop_customers("s1", [c1])

    # Resolving Latin "Ramesh" finds Devanagari "रमेश"
    match, _ = cache.resolve_customer("s1", "Ramesh")
    assert match is not None
    assert match.display_name == "रमेश"

    # Resolving Devanagari finds Devanagari
    match2, _ = cache.resolve_customer("s1", "रमेश")
    assert match2 is not None
    assert match2.id == "c1"


def test_customer_cache_ambiguity_same_name() -> None:
    cache = CustomerCache()
    c1 = CachedCustomer(
        id="c1", shop_id="s1", display_name="Ramesh Kumar", search_key="ramesh kumar"
    )
    c2 = CachedCustomer(
        id="c2", shop_id="s1", display_name="Ramesh Sabziwala", search_key="ramesh sabziwala"
    )
    cache.load_shop_customers("s1", [c1, c2])

    match, amb = cache.resolve_customer("s1", "Ramesh")
    # Ambiguous match returns None and the list of matching candidates
    assert match is None
    assert len(amb) == 2
    assert {c.id for c in amb} == {"c1", "c2"}


def test_customer_cache_invalidation() -> None:
    cache = CustomerCache()
    c1 = CachedCustomer(id="c1", shop_id="s1", display_name="Ramesh", search_key="ramesh")
    cache.load_shop_customers("s1", [c1])
    assert cache.is_cached("s1") is True

    cache.invalidate_shop("s1")
    assert cache.is_cached("s1") is False
    match, _ = cache.resolve_customer("s1", "Ramesh")
    assert match is None


def test_customer_cache_microbenchmark_5000_customers() -> None:
    # §4.6 requirement: customer resolution <= 1 ms p95 with 5,000 customers
    cache = CustomerCache()
    customers = [
        CachedCustomer(
            id=f"c_{i}",
            shop_id="bench_shop",
            display_name=f"Customer{i}",
            search_key=f"customer{i}",
        )
        for i in range(5000)
    ]
    cache.load_shop_customers("bench_shop", customers)

    latencies: list[float] = []
    for i in range(100):
        t0 = time.perf_counter()
        match, _ = cache.resolve_customer("bench_shop", f"Customer{i * 50}")
        dt_ms = (time.perf_counter() - t0) * 1000.0
        latencies.append(dt_ms)
        assert match is not None

    latencies.sort()
    p95 = latencies[int(len(latencies) * 0.95)]
    # Assert strictly under 1.0 ms
    assert p95 <= 1.0
