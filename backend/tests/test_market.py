from fastapi.testclient import TestClient

from backend.main import app
from backend.market import size_of, tier


def test_size_buckets():
    assert size_of(250) == "250" and size_of(500) == "500"
    assert size_of(1000) == "1000" and size_of(750) == "1000" and size_of(2000) == "2000"
    assert size_of(None) is None


def test_tier_uses_own_pack_size_norm():
    th = {"1000": (1300, 1500, 1900), "250": (2400, 2800, 3200)}
    assert tier(1250, 1000, th) == "ucuz"
    assert tier(1600, 1000, th) == "orta"
    assert tier(2300, 1000, th) == "pahali"
    # 250 g paket kendi normuna göre değerlendirilir: 2.500 TL/kg orta sayılır
    assert tier(2500, 250, th) == "orta"
    assert tier(1500, 500, th) is None  # o kovanın normu yok
    assert tier(None, 1000, th) is None


def test_market_endpoint():
    with TestClient(app) as c:
        m = c.get("/api/market").json()
        assert m["size"] == "1000" and isinstance(m["months"], list) and isinstance(m["brands"], list)
        assert c.get("/api/market?size=bogus").json()["size"] == "1000"


def test_chat_validates_input():
    with TestClient(app) as c:
        assert c.post("/api/chat", json={}).status_code == 400
        assert c.post("/api/chat", json={"messages": [{"role": "assistant", "text": "selam"}]}).status_code in (400, 503)
