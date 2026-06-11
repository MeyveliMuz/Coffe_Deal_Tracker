"""Backend duman testleri (CI). Salt-okunur endpoint'ler — Playwright/tarayıcı
gerektirmez; boş DB ile de çalışır. Gerçek tarama (POST /api/scan) burada
çağrılmaz (tarayıcı gerektirir)."""
from fastapi.testclient import TestClient

from backend.main import app


def test_health():
    with TestClient(app) as c:
        assert c.get("/api/health").json() == {"status": "ok"}


def test_config_roundtrip():
    with TestClient(app) as c:
        cfg = c.get("/api/config").json()
        assert "brands" in cfg and "history_days" in cfg
        # aynısını geri yaz — şema doğrulaması
        assert c.put("/api/config", json=cfg).status_code == 200


def test_read_endpoints():
    with TestClient(app) as c:
        assert isinstance(c.get("/api/products").json(), list)
        assert isinstance(c.get("/api/deals").json(), list)
        assert isinstance(c.get("/api/alerts").json(), list)
        assert c.get("/api/scan").json()["running"] in (True, False)
        assert c.get("/api/schedule").status_code == 200


def test_alert_crud():
    with TestClient(app) as c:
        created = c.post(
            "/api/alerts", json={"url": "http://example.test/x", "target_price": 10.0}
        ).json()
        assert created["target_price"] == 10.0
        ids = [a["id"] for a in c.get("/api/alerts").json()]
        assert created["id"] in ids
        assert c.delete(f"/api/alerts/{created['id']}").status_code == 204
