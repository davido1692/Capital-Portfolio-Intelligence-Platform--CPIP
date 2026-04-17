import json
import logging
import os
import random
import threading
import time

import boto3
import psycopg2
import psycopg2.extras
from flask import Flask, jsonify, request

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)

DB_URL = os.environ["DATABASE_URL"]
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
PRICE_UPDATES_TOPIC_ARN = os.environ.get("PRICE_UPDATES_TOPIC_ARN", "")
AWS_ENDPOINT_URL = os.environ.get("AWS_ENDPOINT_URL")
MOCK_PRICES_ENABLED = os.environ.get("MOCK_PRICES_ENABLED", "false").lower() == "true"

SEED_PRICES = {
    "AAPL": 189.00,
    "MSFT": 415.00,
    "GOOGL": 175.00,
    "AMZN": 185.00,
    "TSLA": 175.00,
}


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
        CREATE TABLE IF NOT EXISTS prices (
            symbol     VARCHAR(10)   PRIMARY KEY,
            price      DECIMAL(12,4) NOT NULL,
            updated_at TIMESTAMP     DEFAULT NOW()
        );
    """)
    # Seed initial prices so the system has data from the start
    for symbol, price in SEED_PRICES.items():
        cur.execute("""
            INSERT INTO prices (symbol, price)
            VALUES (%s, %s)
            ON CONFLICT (symbol) DO NOTHING
        """, (symbol, price))
    conn.commit()
    cur.close()
    conn.close()
    logger.info(json.dumps({"event": "db_initialized"}))


def publish_price(symbol, price):
    """Save price to DB and publish event to SNS."""
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO prices (symbol, price, updated_at)
        VALUES (%s, %s, NOW())
        ON CONFLICT (symbol)
        DO UPDATE SET price = EXCLUDED.price, updated_at = NOW()
    """, (symbol, price))
    conn.commit()
    cur.close()
    conn.close()

    if PRICE_UPDATES_TOPIC_ARN:
        sns = get_sns_client()
        sns.publish(
            TopicArn=PRICE_UPDATES_TOPIC_ARN,
            Message=json.dumps({"symbol": symbol, "price": price}),
        )

    logger.info(json.dumps({
        "event": "price_updated",
        "symbol": symbol,
        "price": price,
    }))


def mock_price_generator():
    """Background thread — drifts prices ±2% every 30 seconds."""
    logger.info(json.dumps({"event": "mock_price_generator_started"}))
    current_prices = dict(SEED_PRICES)

    while True:
        time.sleep(30)
        for symbol in current_prices:
            drift = random.uniform(-0.02, 0.02)
            new_price = round(current_prices[symbol] * (1 + drift), 2)
            current_prices[symbol] = new_price
            publish_price(symbol, new_price)


@app.route("/health")
def health():
    try:
        conn = get_db()
        conn.close()
        return jsonify({"status": "ok"})
    except Exception as e:
        return jsonify({"status": "error", "detail": str(e)}), 503


@app.route("/prices", methods=["POST"])
def update_price():
    data = request.get_json()
    symbol = data.get("symbol", "").upper()
    price = data.get("price")

    if not symbol:
        return jsonify({"error": "symbol is required"}), 400
    if price is None or float(price) <= 0:
        return jsonify({"error": "price must be greater than 0"}), 400

    publish_price(symbol, float(price))
    return jsonify({"symbol": symbol, "price": float(price)}), 200


@app.route("/prices/<symbol>")
def get_price(symbol):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM prices WHERE symbol = %s", (symbol.upper(),))
    row = cur.fetchone()
    cur.close()
    conn.close()

    if not row:
        return jsonify({"error": "symbol not found"}), 404
    return jsonify(dict(row))


@app.route("/prices")
def get_all_prices():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT * FROM prices ORDER BY symbol")
    rows = [dict(r) for r in cur.fetchall()]
    cur.close()
    conn.close()
    return jsonify(rows)


if __name__ == "__main__":
    init_db()

    if MOCK_PRICES_ENABLED:
        t = threading.Thread(target=mock_price_generator, daemon=True)
        t.start()

    app.run(host="0.0.0.0", port=5003)
