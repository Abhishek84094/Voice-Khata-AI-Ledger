"""Unit tests for REST endpoints and frontend serving (§4.4, §5.1)."""

from app.main import create_app
from starlette.testclient import TestClient


def test_index_serves_html() -> None:
    app = create_app()
    with TestClient(app) as client:
        res = client.get("/")
        assert res.status_code == 200
        assert "Voice Khata" in res.text


def test_ledger_export_and_data_endpoints() -> None:
    app = create_app()
    with TestClient(app) as client:
        del_res = client.delete("/api/data")
        assert del_res.status_code == 200
        assert del_res.json()["status"] == "purged"

        exp_res = client.get("/api/export")
        assert exp_res.status_code == 200
        data = exp_res.json()
        assert "customers" in data
        assert "events" in data

        led_res = client.get("/api/ledger")
        assert led_res.status_code == 200
        assert isinstance(led_res.json(), list)

        cus_res = client.get("/api/customers")
        assert cus_res.status_code == 200
        assert isinstance(cus_res.json(), list)

        prom_res = client.get("/api/promises")
        assert prom_res.status_code == 200
        assert isinstance(prom_res.json(), list)
