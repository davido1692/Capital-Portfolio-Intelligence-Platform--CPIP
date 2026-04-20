import json
import logging
import os
import threading
import time

import boto3
import psycopg2
import psycopg2.extras
from flask import Flask, jsonify

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)

DB_URL = os.environ["DATABASE_URL"]
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
PORTFOLIO_UPDATES_QUEUE_URL = os.environ.get("PORTFOLIO_UPDATES_QUEUE_URL", "")
PORTFOLIO_RECALC_QUEUE_URL = os.environ.get("PORTFOLIO_RECALC_QUEUE_URL", "")
AWS_ENDPOINT_URL = os.environ.get("AWS_ENDPOINT_URL")


def get_db():
    return psycopg2.connect(DB_URL)


def get_sqs_client():
    kwargs = {"region_name": AWS_REGION}
    if AWS_ENDPOINT_URL:
        kwargs["endpoint_url"] = AWS_ENDPOINT_URL
    return boto3.client("sqs", **kwargs)


def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS positions (
            client_id  VARCHAR(20)    NOT NULL,
            symbol     VARCHAR(10)    NOT NULL,
            quantity   DECIMAL(12,4)  NOT NULL DEFAULT 0,
            updated_at TIMESTAMP      DEFAULT NOW(),
            PRIMARY KEY (client_id, symbol)
        );
    """)
    conn.commit()
    cur.close()
    conn.close()
    logger.info(json.dumps({"event": "db_initialized"}))


def process_trade_event(message):
    body = json.loads(message["Body"])
    client_id = body["client_id"]
    symbol = body["symbol"]
    trade_type = body["type"]
    quantity = float(body["quantity"])

    delta = quantity if trade_type == "BUY" else -quantity

    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO positions (client_id, symbol, quantity)
        VALUES (%s, %s, %s)
        ON CONFLICT (client_id, symbol)
        DO UPDATE SET
            quantity = positions.quantity + EXCLUDED.quantity,
            updated_at = NOW()
    """, (client_id, symbol, delta))
    conn.commit()
    cur.close()
    conn.close()

    logger.info(json.dumps({
        "event": "position_updated",
        "client_id": client_id,
        "symbol": symbol,
        "delta": delta,
    }))


def process_price_update(message):
    body = json.loads(message["Body"])
    symbol = body["symbol"]
    price = float(body["price"])

    logger.info(json.dumps({
        "event": "price_update_received",
        "symbol": symbol,
        "price": price,
    }))


def poll_queue(queue_url, handler, name):
    sqs = get_sqs_client()
    logger.info(json.dumps({"event": f"{name}_poller_started"}))
    while True:
        response = sqs.receive_message(
            QueueUrl=queue_url,
            MaxNumberOfMessages=10,
            WaitTimeSeconds=20,
        )
        messages = response.get("Messages", [])
        for message in messages:
            try:
                handler(message)
                sqs.delete_message(
                    QueueUrl=queue_url,
                    ReceiptHandle=message["ReceiptHandle"],
                )
            except Exception as e:
                logger.error(json.dumps({
                    "event": "message_processing_failed",
                    "queue": name,
                    "error": str(e),
                }))
        if not messages:
            time.sleep(1)


@app.route("/health")
def health():
    try:
        conn = get_db()
        conn.close()
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"status": "error", "detail": str(e)}), 503


@app.route("/portfolios/<client_id>")
def get_portfolio(client_id):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT symbol, quantity, updated_at
        FROM positions
        WHERE client_id = %s AND quantity > 0
    """, (client_id,))
    positions = [dict(row) for row in cur.fetchall()]
    cur.close()
    conn.close()

    return jsonify({
        "client_id": client_id,
        "positions": positions,
    })


if __name__ == "__main__":
    init_db()

    threading.Thread(
        target=poll_queue,
        args=(PORTFOLIO_UPDATES_QUEUE_URL, process_trade_event, "trade"),
        daemon=True,
    ).start()

    threading.Thread(
        target=poll_queue,
        args=(PORTFOLIO_RECALC_QUEUE_URL, process_price_update, "price"),
        daemon=True,
    ).start()

    app.run(host="0.0.0.0", port=5000)
