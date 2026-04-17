import json
import os
import sys
from unittest.mock import MagicMock, patch

# Set required env vars before importing app
os.environ.setdefault("DATABASE_URL", "postgresql://fake/fake")
os.environ.setdefault("AWS_REGION", "us-east-1")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from app import app


def client():
    app.config["TESTING"] = True
    return app.test_client()


def mock_cursor(fetchone_return=None):
    cur = MagicMock()
    cur.fetchone.return_value = fetchone_return
    cur.__enter__ = lambda s: s
    cur.__exit__ = MagicMock(return_value=False)
    return cur


def test_health(mocker):
    mocker.patch("app.get_db")
    resp = client().get("/health")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"


def test_submit_trade_success(mocker):
    cur = mock_cursor(fetchone_return=None)  # no existing trade
    cur.fetchone.side_effect = [
        None,  # idempotency check — trade does not exist
        {      # RETURNING * after insert
            "trade_id": "abc-123",
            "client_id": "C1001",
            "symbol": "AAPL",
            "type": "BUY",
            "quantity": 10,
            "status": "PENDING",
            "created_at": "2026-04-17T00:00:00",
        },
    ]
    conn = MagicMock()
    conn.cursor.return_value = cur
    mocker.patch("app.get_db", return_value=conn)
    mocker.patch("app.get_sns_client")

    resp = client().post("/trades", json={
        "trade_id": "abc-123",
        "client_id": "C1001",
        "symbol": "AAPL",
        "type": "BUY",
        "quantity": 10,
    })
    assert resp.status_code == 201


def test_submit_trade_idempotent(mocker):
    existing = {
        "trade_id": "abc-123",
        "client_id": "C1001",
        "symbol": "AAPL",
        "type": "BUY",
        "quantity": 10,
        "status": "COMPLETED",
        "created_at": "2026-04-17T00:00:00",
    }
    cur = mock_cursor(fetchone_return=existing)
    conn = MagicMock()
    conn.cursor.return_value = cur
    mocker.patch("app.get_db", return_value=conn)

    resp = client().post("/trades", json={
        "trade_id": "abc-123",
        "client_id": "C1001",
        "symbol": "AAPL",
        "type": "BUY",
        "quantity": 10,
    })
    assert resp.status_code == 200


def test_submit_trade_invalid_type(mocker):
    cur = mock_cursor(fetchone_return=None)
    conn = MagicMock()
    conn.cursor.return_value = cur
    mocker.patch("app.get_db", return_value=conn)

    resp = client().post("/trades", json={
        "client_id": "C1001",
        "symbol": "AAPL",
        "type": "HOLD",
        "quantity": 10,
    })
    assert resp.status_code == 400
    assert "BUY or SELL" in resp.get_json()["error"]


def test_submit_trade_invalid_quantity(mocker):
    cur = mock_cursor(fetchone_return=None)
    conn = MagicMock()
    conn.cursor.return_value = cur
    mocker.patch("app.get_db", return_value=conn)

    resp = client().post("/trades", json={
        "client_id": "C1001",
        "symbol": "AAPL",
        "type": "BUY",
        "quantity": 0,
    })
    assert resp.status_code == 400


def test_submit_trade_missing_fields(mocker):
    cur = mock_cursor(fetchone_return=None)
    conn = MagicMock()
    conn.cursor.return_value = cur
    mocker.patch("app.get_db", return_value=conn)

    resp = client().post("/trades", json={"type": "BUY", "quantity": 10})
    assert resp.status_code == 400


def test_get_trade_not_found(mocker):
    cur = mock_cursor(fetchone_return=None)
    conn = MagicMock()
    conn.cursor.return_value = cur
    mocker.patch("app.get_db", return_value=conn)

    resp = client().get("/trades/nonexistent-id")
    assert resp.status_code == 404
