"""Unit tests. DynamoDB is faked with moto, so no AWS account is needed in CI."""
import boto3
import pytest
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
            AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "N"}],
            BillingMode="PAY_PER_REQUEST",
        )
        svc.table.cache_clear()
        svc.seed_products()
        yield
    svc.table.cache_clear()


def test_health():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json["service"] == "product-service"


def test_list_products():
    res = client.get("/products")
    assert res.status_code == 200
    assert len(res.json) == len(svc.SEED_PRODUCTS)


def test_get_missing_product_returns_404():
    assert client.get("/products/999").status_code == 404


def test_reserve_reduces_stock():
    before = client.get("/products/3").json["stock"]
    res = client.post("/products/3/reserve", json={"quantity": 2})
    assert res.status_code == 200
    assert client.get("/products/3").json["stock"] == before - 2


def test_reserve_more_than_stock_is_rejected():
    res = client.post("/products/2/reserve", json={"quantity": 9999})
    assert res.status_code == 409


def test_reserve_invalid_quantity():
    assert client.post("/products/1/reserve", json={"quantity": 0}).status_code == 400


def test_reseeding_does_not_reset_stock():
    client.post("/products/1/reserve", json={"quantity": 3})
    svc.seed_products()   # happens on every deploy
    assert client.get("/products/1").json["stock"] == 10 - 3
