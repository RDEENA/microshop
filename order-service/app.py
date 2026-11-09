"""Order service: saves orders in DynamoDB, calls product-service, emails via SNS."""
import logging
import os
import time
import uuid
from decimal import Decimal
from functools import lru_cache

import boto3
import requests
from botocore.exceptions import BotoCoreError, ClientError
from flask import Flask, jsonify, request

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("order-service")

app = Flask(__name__)
VERSION = os.environ.get("APP_VERSION", "dev")
REGION = os.environ.get("AWS_REGION", "us-east-1")
TABLE_NAME = os.environ.get("ORDERS_TABLE", "microshop-orders")
SNS_TOPIC_ARN = os.environ.get("SNS_TOPIC_ARN", "")
PRODUCT_URL = os.environ.get("PRODUCT_SERVICE_URL", "http://product-service:5001")


@lru_cache(maxsize=1)
def table():
    return boto3.resource("dynamodb", region_name=REGION).Table(TABLE_NAME)


@lru_cache(maxsize=1)
def sns():
    return boto3.client("sns", region_name=REGION)


def clean(item):
    return {k: int(v) if isinstance(v, Decimal) else v for k, v in item.items()}


def create_app():
    """Gunicorn entry point."""
    if not SNS_TOPIC_ARN:
        log.warning("SNS_TOPIC_ARN not set: order emails are disabled")
    return app


def notify(order):
    """Send an email through Amazon SNS. A failed email never cancels the order."""
    if not SNS_TOPIC_ARN:
        return False
    try:
        sns().publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject=f"New MicroShop order #{order['id']}",
            Message=(f"Order #{order['id']}\n"
                     f"Product: {order['product_name']}\n"
                     f"Quantity: {order['quantity']}\n"
                     f"Total: Rs. {order['total']}\n"),
        )
        return True
    except (BotoCoreError, ClientError) as e:
        log.warning("SNS notification failed: %s", e)
        return False


@app.errorhandler(BotoCoreError)
@app.errorhandler(ClientError)
def aws_error(e):
    log.error("AWS error: %s", e)
    return jsonify(error="Database is unavailable right now"), 503


@app.get("/health")
def health():
    return jsonify(status="ok", service="order-service", version=VERSION)


@app.get("/orders")
def list_orders():
    items = [clean(i) for i in table().scan().get("Items", [])]
    items.sort(key=lambda o: o["created_at"], reverse=True)
    return jsonify(items[:20])


@app.post("/orders")
def create_order():
    data = request.get_json(silent=True) or {}
    pid, qty = data.get("product_id"), data.get("quantity", 1)
    if not isinstance(pid, int) or not isinstance(qty, int) or qty < 1:
        return jsonify(error="Send product_id and a positive quantity"), 400

    # 1. Service-to-service call (synchronous REST) to reserve stock
    try:
        res = requests.post(f"{PRODUCT_URL}/products/{pid}/reserve",
                            json={"quantity": qty}, timeout=3)
    except requests.RequestException:
        return jsonify(error="Product service is unavailable, try again shortly"), 503
    if res.status_code != 200:
        return jsonify(res.json()), res.status_code

    # 2. Save the order in DynamoDB
    product = res.json()["product"]
    order = {
        "id": uuid.uuid4().hex[:8],
        "product_id": pid,
        "product_name": product["name"],
        "quantity": qty,
        "total": product["price"] * qty,
        "created_at": int(time.time()),
    }
    table().put_item(Item=order)
    log.info("Order %s placed: %d x %s = Rs. %d",
             order["id"], qty, order["product_name"], order["total"])

    # 3. Email notification through SNS
    order["notified"] = notify(order)
    return jsonify(order), 201


if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=5002, debug=True)
