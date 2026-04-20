import json
import pytest
from unittest.mock import MagicMock, patch

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

os.environ["DATABASE_URL"] = "postgresql://test:test@localhost/test"
os.environ["TRADE_EVENTS_TOPIC_ARN"] = "arn:aws:sns:us-east-1:000000000000:test"

import app


def test_health_success(mocker):
    mock_conn = MagicMock()
    mocker.patch("app.get_db", return_value=mock_conn)

    client = app.app.test_client()
    response = client.get("/health")

    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["status"] == "ok"


def test_health_failure(mocker):
    mocker.patch("app.get_db", side_effect=Exception("DB connection failed"))

    client = app.app.test_client()
    response = client.get("/health")

    assert response.status_code == 503
    data = json.loads(response.data)
    assert data["status"] == "error"


def test_submit_trade_success(mocker):
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_cur.fetchone.side_effect = [None, {"trade_id": "t1", "client_id": "C001", "symbol": "AAPL", "type": "BUY", "quantity": 10, "status": "PENDING"}]
    mock_conn.cursor.return_value = mock_cur
    mocker.patch("app.get_db", return_value=mock_conn)
    mocker.patch("app.get_sns_client", return_value=MagicMock())

    client = app.app.test_client()
    response = client.post("/trades", json={
        "client_id": "C001",
        "symbol": "AAPL",
        "type": "BUY",
        "quantity": 10,
    })

    assert response.status_code == 201


def test_submit_trade_missing_fields(mocker):
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_cur.fetchone.return_value = None
    mock_conn.cursor.return_value = mock_cur
    mocker.patch("app.get_db", return_value=mock_conn)

    client = app.app.test_client()
    response = client.post("/trades", json={"symbol": "AAPL"})

    assert response.status_code == 400


def test_submit_trade_invalid_type(mocker):
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_cur.fetchone.return_value = None
    mock_conn.cursor.return_value = mock_cur
    mocker.patch("app.get_db", return_value=mock_conn)

    client = app.app.test_client()
    response = client.post("/trades", json={
        "client_id": "C001",
        "symbol": "AAPL",
        "type": "HOLD",
        "quantity": 10,
    })

    assert response.status_code == 400


def test_get_trade_not_found(mocker):
    mock_conn = MagicMock()
    mock_cur = MagicMock()
    mock_cur.fetchone.return_value = None
    mock_conn.cursor.return_value = mock_cur
    mocker.patch("app.get_db", return_value=mock_conn)

    client = app.app.test_client()
    response = client.get("/trades/nonexistent-id")

    assert response.status_code == 404
