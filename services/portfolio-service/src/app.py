import json
import logging
import os
import threading
import time
from datetime import datetime, timezone

import boto3
import psycopg2
import psycopg2.extras
from flask import Flask, jsonify, request

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
        CREATE TABLE IF NOT EXISTS clients (
            client_id  VARCHAR(20)   PRIMARY KEY,
            name       VARCHAR(100)  NOT NULL,
            email      VARCHAR(100)  NOT NULL,
            created_at TIMESTAMP     DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS holdings (
            id         SERIAL        PRIMARY KEY,
            client_id  VARCHAR(20)   REFERENCES clients(client_id),
            symbol     VARCHAR(10)   NOT NULL,
            shares     DECIMAL(12,4) NOT NULL,
            updated_at TIMESTAMP     DEFAULT NOW(),
            UNIQUE (client_id, symbol)
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
        CREATE TABLE IF NOT EXISTS prices (
            symbol     VARCHAR(10)   PRIMARY KEY,
            price      DECIMAL(12,4) NOT NULL,
            updated_at TIMESTAMP     DEFAULT NOW()
        );
    """)
    conn.commit()
    cur.close()
    conn.close()
    logger.info(json.dumps({"event": "db_initialized"}))


def compute_portfolio(client_id):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        SELECT h.symbol,
               h.shares,
               COALESCE(p.price, 0)              AS price,
               h.shares * COALESCE(p.price, 0)   AS value
        FROM holdings h
        LEFT JOIN prices p ON h.symbol = p.symbol
        WHERE h.client_id = %s
    """, (client_id,))
    holdings = [dict(r) for r in cur.fetchall()]
    cur.close()
    conn.close()

    return {
        "client_id": client_id,
        "holdings": [
            {
                "symbol": h["symbol"],
                "shares": float(h["shares"]),
                "price": float(h["price"]),
                "value": float(h["value"]),
            }
            for h in holdings
        ],
        "total_value": sum(float(h["value"]) for h in holdings),
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }


def process_trade_event(message):
    """
    Handles a trade-completed event from portfolio-updates-queue.
    Updates holdings (BUY adds shares, SELL removes shares) and marks trade COMPLETED.
    """
    body = json.loads(message["Body"])
    # SNS wraps the actual message in an envelope — unwrap it
    if "Message" in body:
        body = json.loads(body["Message"])

    trade_id  = body["trade_id"]
    client_id = body["client_id"]
    symbol    = body["symbol"]
    trade_type = body["type"]
    quantity  = float(body["quantity"])

    start = time.time()
    conn = get_db()
    cur = conn.cursor()

    if trade_type == "BUY":
        cur.execute("""
            INSERT INTO holdings (client_id, symbol, shares, updated_at)
            VALUES (%s, %s, %s, NOW())
            ON CONFLICT (client_id, symbol)
            DO UPDATE SET shares = holdings.shares + EXCLUDED.shares,
                          updated_at = NOW()
        """, (client_id, symbol, quantity))
    elif trade_type == "SELL":
        cur.execute("""
            UPDATE holdings
            SET shares = shares - %s, updated_at = NOW()
            WHERE client_id = %s AND symbol = %s
        """, (quantity, client_id, symbol))

    cur.execute(
        "UPDATE trades SET status = 'COMPLETED' WHERE trade_id = %s",
        (trade_id,)
    )
    conn.commit()
    cur.close()
    conn.close()

    elapsed = int((time.time() - start) * 1000)
    logger.info(json.dumps({
        "event": "trade_processed",
        "trade_id": trade_id,
        "client_id": client_id,
        "symbol": symbol,
        "type": trade_type,
        "quantity": quantity,
        "duration_ms": elapsed,
    }))


def process_price_event(message):
    """
    Handles a price-update event from portfolio-recalc-queue.
    Finds all clients holding the symbol and logs their new portfolio value.
    """
    body = json.loads(message["Body"])
    if "Message" in body:
        body = json.loads(body["Message"])

    symbol = body["symbol"]
    price  = float(body["price"])

    start = time.time()
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT DISTINCT client_id FROM holdings WHERE symbol = %s",
        (symbol,)
    )
    affected = [r["client_id"] for r in cur.fetchall()]
    cur.close()
    conn.close()

    elapsed = int((time.time() - start) * 1000)
    for client_id in affected:
        portfolio = compute_portfolio(client_id)
        logger.info(json.dumps({
            "event": "portfolio_recalculated",
            "client_id": client_id,
            "trigger_symbol": symbol,
            "new_price": price,
            "total_value": portfolio["total_value"],
            "duration_ms": elapsed,
        }))


def poll_queue(queue_url, handler, queue_name):
    """Long-polls an SQS queue, calls handler per message, deletes on success."""
    if not queue_url:
        logger.info(json.dumps({"event": "queue_skipped", "queue": queue_name}))
        return

    sqs = get_sqs_client()
    logger.info(json.dumps({"event": "polling_started", "queue": queue_name}))

    while True:
        try:
            resp = sqs.receive_message(
                QueueUrl=queue_url,
                MaxNumberOfMessages=10,
                WaitTimeSeconds=20,  # long polling — reduces empty responses
            )
            for msg in resp.get("Messages", []):
                try:
                    handler(msg)
                    sqs.delete_message(
                        QueueUrl=queue_url,
                        ReceiptHandle=msg["ReceiptHandle"]
                    )
                except Exception as e:
                    logger.error(json.dumps({
                        "event": "message_processing_error",
                        "queue": queue_name,
                        "error": str(e),
                    }))
                    # Do NOT delete — message returns to queue after visibility timeout
                    # After max_receive_count retries it goes to the DLQ
        except Exception as e:
            logger.error(json.dumps({"event": "poll_error", "queue": queue_name, "error": str(e)}))
            time.sleep(5)


@app.route("/health")
def health():
    try:
        conn = get_db()
        conn.close()
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"status": "error", "detail": str(e)}), 503


@app.route("/portfolios", methods=["POST"])
def create_portfolio():
    data = request.get_json()
    client_id = data.get("client_id")
    name      = data.get("name")
    email     = data.get("email")

    if not all([client_id, name, email]):
        return jsonify({"error": "client_id, name, and email are required"}), 400

    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO clients (client_id, name, email) VALUES (%s, %s, %s)",
            (client_id, name, email)
        )
        conn.commit()
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        return jsonify({"error": "client already exists"}), 409
    finally:
        cur.close()
        conn.close()

    logger.info(json.dumps({"event": "client_created", "client_id": client_id}))
    return jsonify({"client_id": client_id, "name": name, "email": email}), 201


@app.route("/portfolios/<client_id>")
def get_portfolio(client_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT client_id FROM clients WHERE client_id = %s", (client_id,))
    if not cur.fetchone():
        cur.close()
        conn.close()
        return jsonify({"error": "client not found"}), 404
    cur.close()
    conn.close()
    return jsonify(compute_portfolio(client_id))


@app.route("/portfolios/<client_id>/holdings")
def get_holdings(client_id):
    portfolio = compute_portfolio(client_id)
    return jsonify({"client_id": client_id, "holdings": portfolio["holdings"]})


if __name__ == "__main__":
    init_db()

    t1 = threading.Thread(
        target=poll_queue,
        args=(PORTFOLIO_UPDATES_QUEUE_URL, process_trade_event, "portfolio-updates"),
        daemon=True,
    )
    t2 = threading.Thread(
        target=poll_queue,
        args=(PORTFOLIO_RECALC_QUEUE_URL, process_price_event, "portfolio-recalc"),
        daemon=True,
    )
    t1.start()
    t2.start()

    app.run(host="0.0.0.0", port=5001)
