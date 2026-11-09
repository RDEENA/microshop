"""Unit tests. DynamoDB + SNS are faked with moto; product-service is mocked."""
from unittest.mock import MagicMock, patch

import boto3
import pytest
import requests
from moto import mock_aws

import app as svc

client = svc.app.test_client()


@pytest.fixture(autouse=True)
def fake_aws(monkeypatch):
    for k, v in {"AWS_ACCESS_KEY_ID": "test", "AWS_SECRET_ACCESS_KEY": "test",
                 "AWS_SESSION_TOKEN": "test", "AWS_DEFAULT_REGION": "us-east-1"}.items():
        monkeypatch.setenv(k, v)
    with mock_aws():
        boto3.resource("dynamodb", region_name=svc.REGION).create_table(
            TableName=svc.TABLE_NAME,
            KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        arn = boto3.client("sns", region_name=svc.REGION).create_topic(Name="orders")["TopicArn"]
        monkeypatch.setattr(svc, "SNS_TOPIC_ARN", arn)
        svc.table.cache_clear()
        svc.sns.cache_clear()
        yield
    svc.table.cache_clear()
    svc.sns.cache_clear()


def product_reply(status, body):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = body
    return r


BOOK = {"product": {"id": 1, "name": "Book", "price": 100, "stock": 5}}


def test_health():
    assert client.get("/health").json["service"] == "order-service"


@patch("app.requests.post", return_value=product_reply(200, BOOK))
def test_order_is_saved_and_notified(mock_post):
    res = client.post("/orders", json={"product_id": 1, "quantity": 3})
    assert res.status_code == 201
    assert res.json["total"] == 300
    assert res.json["notified"] is True
    orders = client.get("/orders").json
    assert len(orders) == 1 and orders[0]["product_name"] == "Book"


@patch("app.requests.post", return_value=product_reply(200, BOOK))
def test_order_still_works_without_sns(mock_post, monkeypatch):
    monkeypatch.setattr(svc, "SNS_TOPIC_ARN", "")
    res = client.post("/orders", json={"product_id": 1, "quantity": 1})
    assert res.status_code == 201
    assert res.json["notified"] is False


@patch("app.requests.post", return_value=product_reply(409, {"error": "Only 1 left in stock"}))
def test_out_of_stock_is_passed_through(mock_post):
    res = client.post("/orders", json={"product_id": 1, "quantity": 5})
    assert res.status_code == 409
    assert client.get("/orders").json == []


@patch("app.requests.post", side_effect=requests.ConnectionError)
def test_product_service_down_returns_503(mock_post):
    assert client.post("/orders", json={"product_id": 1, "quantity": 1}).status_code == 503


def test_invalid_input():
    assert client.post("/orders", json={"product_id": "abc"}).status_code == 400
