import json
import logging
import os
import uuid

import boto3
import psycopg2
import psycopg2.extras
from flask import Flask, jsonify, request

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)

DB_URL = os.environ["DATABASE_URL"]
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
TRADE_EVENTS_TOPIC_ARN = os.environ.get("TRADE_EVENTS_TOPIC_ARN", "")
AWS_ENDPOINT_URL = os.environ.get("AWS_ENDPOINT_URL")


def get_db():
    return psycopg2.connect(DB_URL)


def get_sns_client():
    kwargs = {"region_name": AWS_REGION}
    if AWS_ENDPOINT_URL:
        kwargs["endpoint_url"] = AWS_ENDPOINT_URL
    return boto3.client("sns", **kwargs)


def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS clients (
            client_id  VARCHAR(20)   PRIMARY KEY,
            name       VARCHAR(100)  NOT NULL,
            email      VARCHAR(100)  NOT NULL,
            created_at TIMESTAMP     DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS trades (
            trade_id   VARCHAR(36)   PRIMARY KEY,
            client_id  VARCHAR(20)   NOT NULL,
            symbol     VARCHAR(10)   NOT NULL,
            type       VARCHAR(4)    NOT NULL,
            quantity   DECIMAL(12,4) NOT NULL,
            status     VARCHAR(20)   DEFAULT 'PENDING',
            created_at TIMESTAMP     DEFAULT NOW()
        );
    """)
    conn.commit()
    cur.close()
    conn.close()
    logger.info(json.dumps({"event": "db_initialized"}))


@app.route("/health")
def health():
    try:
        conn = get_db()
        conn.close()
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"status": "error", "detail": str(e)}), 503


@app.route("/trades", methods=["POST"])
def submit_trade():
    data = request.get_json()

    trade_id = data.get("trade_id") or str(uuid.uuid4())
    client_id = data.get("client_id")
    symbol = data.get("symbol")
    trade_type = data.get("type", "").upper()
    quantity = data.get("quantity")

    # Idempotency check
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM trades WHERE trade_id = %s", (trade_id,))
    existing = cur.fetchone()
    if existing:
        cur.close()
        conn.close()
        return jsonify(dict(existing)), 200

    # Validation
    if not all([client_id, symbol, quantity]):
        return jsonify({"error": "client_id, symbol, and quantity are required"}), 400
    if trade_type not in ("BUY", "SELL"):
        return jsonify({"error": "type must be BUY or SELL"}), 400
    if float(quantity) <= 0:
        return jsonify({"error": "quantity must be greater than 0"}), 400

    # Save to DB
    cur.execute("""
        INSERT INTO trades (trade_id, client_id, symbol, type, quantity, status)
        VALUES (%s, %s, %s, %s, %s, 'PENDING')
        RETURNING *
    """, (trade_id, client_id, symbol, trade_type, quantity))
    trade = dict(cur.fetchone())
    conn.commit()
    cur.close()
    conn.close()

    # Publish to SNS
    if TRADE_EVENTS_TOPIC_ARN:
        sns = get_sns_client()
        sns.publish(
            TopicArn=TRADE_EVENTS_TOPIC_ARN,
            Message=json.dumps({
                "trade_id": trade_id,
                "client_id": client_id,
                "symbol": symbol,
                "type": trade_type,
                "quantity": float(quantity),
            }),
        )

    logger.info(json.dumps({
        "event": "trade_submitted",
        "trade_id": trade_id,
        "client_id": client_id,
        "symbol": symbol,
        "type": trade_type,
        "quantity": float(quantity),
    }))

    return jsonify(trade), 201


@app.route("/trades/<trade_id>")
def get_trade(trade_id):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM trades WHERE trade_id = %s", (trade_id,))
    trade = cur.fetchone()
    cur.close()
    conn.close()

    if not trade:
        return jsonify({"error": "trade not found"}), 404
    return jsonify(dict(trade))


if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5002)
