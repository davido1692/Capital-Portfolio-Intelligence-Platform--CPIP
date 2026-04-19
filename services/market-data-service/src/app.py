import json
import logging
import os

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
            symbol     VARCHAR(10)    NOT NULL,
            price      DECIMAL(12,4)  NOT NULL,
            updated_at TIMESTAMP      DEFAULT NOW(),
            PRIMARY KEY (symbol)
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

@app.route("/prices", methods=["POST"])
def update_price():
    data = request.get_json()

    symbol = data.get("symbol", "").upper()
    price = data.get("price")

    if not symbol:
        return jsonify({"error": "symbol is required"}), 400
    if price is None or float(price) <= 0:
        return jsonify({"error": "price must be greater than 0"}), 400

    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("""
        INSERT INTO prices (symbol, price, updated_at)
        VALUES (%s, %s, NOW())
        ON CONFLICT (symbol)
        DO UPDATE SET price = EXCLUDED.price, updated_at = NOW()
        RETURNING *
    """, (symbol, price))
    result = dict(cur.fetchone())
    conn.commit()
    cur.close()
    conn.close()

    logger.info(json.dumps({
        "event": "price_updated",
        "symbol": symbol,
        "price": float(price),
    }))

    return jsonify(result), 200

@app.route("/prices/<symbol>")      
def get_price(symbol):                                                                                   
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)                                     
    cur.execute("SELECT * FROM prices WHERE symbol = %s", (symbol.upper(),))
    price = cur.fetchone()
    cur.close()
    conn.close()

    if not price:
          return jsonify({"error": "symbol not found"}), 404
    return jsonify(dict(price))

if __name__ == "__main__":    
    init_db()                                                                                            
    app.run(host="0.0.0.0", port=5001)   