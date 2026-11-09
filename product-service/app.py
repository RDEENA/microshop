"""Product service: product catalogue and stock, stored in Amazon DynamoDB."""
import logging
import os
from decimal import Decimal
from functools import lru_cache

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from flask import Flask, jsonify, request

# Logs go to stdout -> Docker -> Amazon CloudWatch Logs (awslogs driver)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("product-service")

app = Flask(__name__)
VERSION = os.environ.get("APP_VERSION", "dev")
REGION = os.environ.get("AWS_REGION", "us-east-1")
TABLE_NAME = os.environ.get("PRODUCTS_TABLE", "microshop-products")

# Starter catalogue. Adding an item here and pushing to GitHub adds it to the live shop.
SEED_PRODUCTS = [
    {"id": 1, "name": "Cloud Computing Textbook", "price": 650, "stock": 10},
    {"id": 2, "name": "Raspberry Pi 5", "price": 7800, "stock": 5},
    {"id": 3, "name": "USB-C Hub", "price": 1499, "stock": 20},
    {"id": 4, "name": "Mechanical Keyboard", "price": 3299, "stock": 8},
    {"id": 5, "name": "Wireless Mouse", "price": 899, "stock": 15},
]


@lru_cache(maxsize=1)
def table():
    # Credentials come from the EC2 IAM role automatically: no keys in code
    return boto3.resource("dynamodb", region_name=REGION).Table(TABLE_NAME)


def clean(item):
    """DynamoDB returns numbers as Decimal; convert them for JSON."""
    return {k: int(v) if isinstance(v, Decimal) else v for k, v in item.items()}


def seed_products():
    """Insert starter products that don't exist yet. Never overwrites existing stock."""
    for product in SEED_PRODUCTS:
        try:
            table().put_item(Item=product, ConditionExpression="attribute_not_exists(id)")
            log.info("Seeded product: %s", product["name"])
        except ClientError as e:
            if e.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise


def create_app():
    """Gunicorn entry point: seed the table once at startup."""
    try:
        seed_products()
    except (BotoCoreError, ClientError) as e:
        log.error("Could not reach DynamoDB table %s: %s", TABLE_NAME, e)
    return app


@app.errorhandler(BotoCoreError)
@app.errorhandler(ClientError)
def aws_error(e):
    log.error("AWS error: %s", e)
    return jsonify(error="Database is unavailable right now"), 503


@app.get("/health")
def health():
    return jsonify(status="ok", service="product-service", version=VERSION)


@app.get("/products")
def list_products():
    items = table().scan().get("Items", [])
    return jsonify(sorted((clean(i) for i in items), key=lambda p: p["id"]))


@app.get("/products/<int:pid>")
def get_product(pid):
    item = table().get_item(Key={"id": pid}).get("Item")
    if item is None:
        return jsonify(error="Product not found"), 404
    return jsonify(clean(item))


@app.post("/products/<int:pid>/reserve")
def reserve(pid):
    """Called by order-service. Atomic: two buyers can never take the last item."""
    qty = (request.get_json(silent=True) or {}).get("quantity", 1)
    if not isinstance(qty, int) or isinstance(qty, bool) or qty < 1:
        return jsonify(error="Quantity must be a positive whole number"), 400

    try:
        res = table().update_item(
            Key={"id": pid},
            UpdateExpression="SET stock = stock - :q",
            ConditionExpression="attribute_exists(id) AND stock >= :q",
            ExpressionAttributeValues={":q": qty},
            ReturnValues="ALL_NEW",
        )
    except ClientError as e:
        if e.response["Error"]["Code"] != "ConditionalCheckFailedException":
            raise
        item = table().get_item(Key={"id": pid}).get("Item")
        if item is None:
            return jsonify(error="Product not found"), 404
        return jsonify(error=f"Only {int(item['stock'])} left in stock"), 409

    product = clean(res["Attributes"])
    log.info("Reserved %d x %s (%d left)", qty, product["name"], product["stock"])
    return jsonify(product=product)


if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=5001, debug=True)
