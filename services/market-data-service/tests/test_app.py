import os
import sys
from unittest.mock import MagicMock

os.environ.setdefault("DATABASE_URL", "postgresql://fake/fake")
os.environ.setdefault("AWS_REGION", "us-east-1")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from app import app


def client():
    app.config["TESTING"] = True
    return app.test_client()


def test_health(mocker):
    mocker.patch("app.get_db")
    resp = client().get("/health")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"


def test_update_price_success(mocker):
    mocker.patch("app.publish_price")
    resp = client().post("/prices", json={"symbol": "AAPL", "price": 189.25})
    assert resp.status_code == 200
    assert resp.get_json()["symbol"] == "AAPL"


def test_update_price_invalid_price(mocker):
    resp = client().post("/prices", json={"symbol": "AAPL", "price": -10})
    assert resp.status_code == 400


def test_update_price_zero(mocker):
    resp = client().post("/prices", json={"symbol": "AAPL", "price": 0})
    assert resp.status_code == 400


def test_update_price_missing_symbol(mocker):
    resp = client().post("/prices", json={"price": 189.25})
    assert resp.status_code == 400


def test_get_price_not_found(mocker):
    cur = MagicMock()
    cur.fetchone.return_value = None
    conn = MagicMock()
    conn.cursor.return_value = cur
    mocker.patch("app.get_db", return_value=conn)

    resp = client().get("/prices/FAKE")
    assert resp.status_code == 404


def test_get_all_prices(mocker):
    cur = MagicMock()
    cur.__iter__ = MagicMock(return_value=iter([]))
    cur.fetchall.return_value = []
    conn = MagicMock()
    conn.cursor.return_value = cur
    mocker.patch("app.get_db", return_value=conn)

    resp = client().get("/prices")
    assert resp.status_code == 200
