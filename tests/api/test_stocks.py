from decimal import Decimal

import pytest
from django.test import Client

pytestmark = pytest.mark.django_db

JSON = "application/json"


def _request(client: Client, method: str, url: str):
    if method == "put":
        return client.put(url, {"last_price": "3"}, JSON)
    return getattr(client, method)(url)


def test_stock_crud(client: Client):
    response = client.post("/api/stocks", {"symbol": "meta", "last_price": "10"}, JSON)
    assert response.status_code == 201
    assert response.json()["symbol"] == "META"

    response = client.post("/api/stocks", {"symbol": "META", "last_price": "1"}, JSON)
    assert response.status_code == 409

    response = client.put("/api/stocks/META", {"last_price": "12.5"}, JSON)
    assert response.status_code == 200
    assert Decimal(response.json()["last_price"]) == Decimal("12.5")

    assert client.delete("/api/stocks/META").status_code == 204
    assert client.get("/api/stocks/META").status_code == 404


def test_stock_duplicate_message(client: Client, stocks):
    response = client.post("/api/stocks", {"symbol": " a ", "last_price": "1"}, JSON)
    assert response.status_code == 409
    assert response.json() == {"detail": "Stock A already exists"}


def test_stock_list_is_ordered_by_symbol(client: Client):
    assert client.get("/api/stocks").json() == []
    for symbol in ("C", "A", "B"):
        client.post("/api/stocks", {"symbol": symbol, "last_price": "1"}, JSON)

    response = client.get("/api/stocks")
    assert response.status_code == 200
    assert [s["symbol"] for s in response.json()] == ["A", "B", "C"]


@pytest.mark.parametrize("method", ["get", "put", "delete"])
def test_stock_lookup_is_case_insensitive(client: Client, stocks, method: str):
    response = _request(client, method, "/api/stocks/b")
    assert response.status_code == {"get": 200, "put": 200, "delete": 204}[method]


def test_stock_get(client: Client, stocks):
    body = client.get("/api/stocks/B").json()
    assert body["symbol"] == "B"
    assert Decimal(body["last_price"]) == Decimal("2.5")


@pytest.mark.parametrize("method", ["get", "put", "delete"])
def test_stock_not_found(client: Client, method: str):
    assert _request(client, method, "/api/stocks/Z").status_code == 404


@pytest.mark.parametrize(
    "payload",
    [
        {"symbol": "A", "last_price": "0"},
        {"symbol": "A", "last_price": "-1"},
        {"symbol": "", "last_price": "1"},
        {"symbol": "X" * 17, "last_price": "1"},
        {"symbol": "A"},
    ],
)
def test_stock_create_invalid(client: Client, payload: dict):
    assert client.post("/api/stocks", payload, JSON).status_code == 422
    assert client.get("/api/stocks").json() == []


@pytest.mark.parametrize("price", ["0", "-1", "abc"])
def test_stock_update_invalid_price(client: Client, stocks, price: str):
    response = client.put("/api/stocks/A", {"last_price": price}, JSON)
    assert response.status_code == 422
    assert Decimal(client.get("/api/stocks/A").json()["last_price"]) == 1


def test_delete_held_stock_conflicts(client: Client, portfolio_id: int):
    response = client.delete("/api/stocks/A")
    assert response.status_code == 409
    assert response.json() == {"detail": "Stock A is held by a portfolio"}
    assert client.get("/api/stocks/A").status_code == 200
