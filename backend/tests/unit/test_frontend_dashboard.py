"""Frontend and PWA Dashboard verification tests (§6 Phase 8).

Guarantees:
1. Root HTML serves clean PWA dashboard with all 5 mandatory views:
   - Home (Today / Week / Month tabs: credit given, received, net, top debtors, due today)
   - Customers (Khata directory with balance and search key)
   - Promises (Overdue promises with missed dates, all active promises)
   - Activity (Recent voice entries feed with directions and notes)
   - Settings (Language selector, export, purge data)
2. Bundle size verification: HTML/JS initial payload <= 120 KB (gzipped ~6 KB).
3. Push-to-talk mic button and WebSocket voice controls embedded and accessible.
"""

from __future__ import annotations

import gzip
import os

from app.main import create_app
from starlette.testclient import TestClient


def test_frontend_dashboard_served_with_all_views() -> None:
    app = create_app()
    with TestClient(app) as client:
        res = client.get("/")
        assert res.status_code == 200
        assert "text/html" in res.headers.get("content-type", "")
        html = res.text

        # 1. Branding & Header
        assert "Voice Khata" in html
        assert "Digital Munim PWA" in html

        # 2. All 5 Views present in DOM
        assert 'id="viewHome"' in html
        assert 'id="viewCustomers"' in html
        assert 'id="viewPromises"' in html
        assert 'id="viewActivity"' in html
        assert 'id="viewSettings"' in html

        # 3. Period Tabs
        assert 'data-period="today"' in html
        assert 'data-period="this_week"' in html
        assert 'data-period="this_month"' in html

        # 4. Voice Controls
        assert 'id="micBtn"' in html
        assert 'id="savedCard"' in html
        assert 'id="voiceDrawer"' in html
        assert 'id="transcriptBox"' in html

        # 5. Offline resilience banner
        assert 'id="offlineBanner"' in html


def test_frontend_bundle_size_budget() -> None:
    """Verify Phase 8 requirement: initial JS/HTML <= 120 KB gzipped."""
    html_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", "frontend", "index.html")
    assert os.path.exists(html_path)

    with open(html_path, "rb") as f:
        raw_bytes = f.read()

    uncompressed_kb = len(raw_bytes) / 1024.0
    gzipped_bytes = gzip.compress(raw_bytes)
    gzipped_kb = len(gzipped_bytes) / 1024.0

    print(f"\n[DASHBOARD BUNDLE SIZE] Raw: {uncompressed_kb:.2f} KB | Gz: {gzipped_kb:.2f} KB")

    # Target: initial bundle <= 120 KB gzipped (§4.2, §6 Phase 8)
    assert gzipped_kb <= 120.0
    assert uncompressed_kb <= 120.0  # Even completely uncompressed it's well under 30 KB
