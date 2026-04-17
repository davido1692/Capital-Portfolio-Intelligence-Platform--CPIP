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


def test_create_portfolio_success(mocker):
    cur = MagicMock()
    conn = MagicMock()
    conn.cursor.return_value = cur
    mocker.patch("app.get_db", return_value=conn)

    resp = client().post("/portfolios", json={
        "client_id": "C1001",
        "name": "David O",
        "email": "david@example.com",
    })
    assert resp.status_code == 201
    assert resp.get_json()["client_id"] == "C1001"


def test_create_portfolio_missing_fields(mocker):
    resp = client().post("/portfolios", json={"client_id": "C1001"})
    assert resp.status_code == 400


def test_get_portfolio_not_found(mocker):
    cur = MagicMock()
    cur.fetchone.return_value = None
    conn = MagicMock()
    conn.cursor.return_value = cur
    mocker.patch("app.get_db", return_value=conn)

    resp = client().get("/portfolios/UNKNOWN")
    assert resp.status_code == 404


def test_get_portfolio_success(mocker):
    cur = MagicMock()
    cur.fetchone.return_value = ("C1001",)
    cur.fetchall.return_value = []
    conn = MagicMock()
    conn.cursor.return_value = cur
    mocker.patch("app.get_db", return_value=conn)

    resp = client().get("/portfolios/C1001")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["client_id"] == "C1001"
    assert data["total_value"] == 0.0
